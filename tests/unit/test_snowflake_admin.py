"""Free tests for the Snowflake setup helper (infra/snowflake_admin.py). No network."""

import pytest

from infra import snowflake_admin as admin


def test_account_identifier_splits_into_organization_and_account():
    assert admin.split_account("MYORG-MY_ACCOUNT") == ("MYORG", "MY_ACCOUNT")


@pytest.mark.parametrize("bad", ["", "NOHYPHEN", "-ACCOUNT", "ORG-", "xy12345.ca-central-1.aws"])
def test_account_identifier_without_org_and_account_is_refused(bad):
    with pytest.raises(admin.SetupError):
        admin.split_account(bad)


def test_key_pair_private_key_is_encrypted_and_opens_with_the_passphrase(tmp_path):
    from cryptography.hazmat.primitives import serialization

    admin.write_key_pair(tmp_path, "builder", "correct horse")

    private_pem = (tmp_path / "builder.p8").read_bytes()
    assert b"ENCRYPTED PRIVATE KEY" in private_pem
    with pytest.raises((TypeError, ValueError)):
        serialization.load_pem_private_key(private_pem, password=None)
    key = serialization.load_pem_private_key(private_pem, password=b"correct horse")
    assert key.key_size == 2048


def test_key_pair_public_key_is_one_line_without_header(tmp_path):
    body = admin.write_key_pair(tmp_path, "builder", "pw")

    assert "\n" not in body and "BEGIN" not in body
    assert body in (tmp_path / "builder.pub").read_text().replace("\n", "")


def test_existing_key_pair_is_never_overwritten(tmp_path):
    first = admin.write_key_pair(tmp_path, "sim", "pw")
    second = admin.write_key_pair(tmp_path, "sim", "pw")

    assert first == second


ENV = {
    "SNOWFLAKE_ACCOUNT": "MYORG-MY_ACCOUNT",
    "SNOWFLAKE_PRIVATE_KEY_PASSPHRASE": "s3cret",
}


def test_settings_name_the_missing_variable():
    with pytest.raises(admin.SetupError, match="SNOWFLAKE_PRIVATE_KEY_PASSPHRASE"):
        admin.Settings.from_env({"SNOWFLAKE_ACCOUNT": "MYORG-MY_ACCOUNT"})


def test_settings_keep_keys_and_state_outside_the_repo_by_default(tmp_path):
    settings = admin.Settings.from_env(ENV, home=tmp_path)

    assert settings.local_dir == tmp_path / ".agentic-jev-trader" / "snowflake"
    assert settings.keys_dir == settings.local_dir / "keys"


def test_settings_local_folder_can_be_moved(tmp_path):
    settings = admin.Settings.from_env({**ENV, "SNOWFLAKE_LOCAL_DIR": str(tmp_path / "elsewhere")})

    assert settings.local_dir == tmp_path / "elsewhere"


def test_terraform_gets_account_admin_login_and_key_folder(tmp_path):
    settings = admin.Settings.from_env({**ENV, "SNOWFLAKE_LOCAL_DIR": str(tmp_path)})

    env = admin.terraform_env(settings)

    assert env["TF_VAR_organization_name"] == "MYORG"
    assert env["TF_VAR_account_name"] == "MY_ACCOUNT"
    assert env["TF_VAR_admin_user"] == "TRADING_AGENT_TERRAFORM_SVC"
    assert env["TF_VAR_admin_private_key_path"] == str(tmp_path / "keys" / "terraform.p8")
    assert env["TF_VAR_public_keys_dir"] == str(tmp_path / "keys")
    assert env["TF_VAR_private_key_passphrase"] == "s3cret"


def test_schemachange_runs_as_the_migrations_login_on_the_given_database(tmp_path):
    settings = admin.Settings.from_env({**ENV, "SNOWFLAKE_LOCAL_DIR": str(tmp_path)})

    argv = admin.schemachange_command(settings, "TRADING_AGENT_TEST")

    def value_after(flag):
        return argv[argv.index(flag) + 1]

    assert value_after("--snowflake-account") == "MYORG-MY_ACCOUNT"
    assert value_after("--snowflake-user") == "TRADING_AGENT_MIGRATIONS_SVC"
    assert value_after("--snowflake-role") == "TRADING_AGENT_MIGRATIONS"
    assert value_after("--snowflake-database") == "TRADING_AGENT_TEST"
    assert value_after("--snowflake-authenticator") == "snowflake_jwt"
    assert value_after("--snowflake-private-key-file") == str(tmp_path / "keys" / "migrations.p8")
    assert value_after("--schemachange-change-history-table") == "TRADING_AGENT_TEST.METADATA.CHANGE_HISTORY"
    assert "--schemachange-create-change-history-table" in argv
    assert "s3cret" not in " ".join(argv)
