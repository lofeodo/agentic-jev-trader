"""Free tests for the kind deploy helper (infra/deploy.py): what it hands Terraform. No network,
no Terraform."""

import pytest

from infra import deploy
from infra.snowflake_admin import Settings, SetupError

ENV = {
    "SNOWFLAKE_ACCOUNT": "MYORG-MY_ACCOUNT",
    "SNOWFLAKE_PRIVATE_KEY_FILE_PWD": "s3cret",
    "TWELVE_DATA_API_KEY": "td-key",
    "TYPESAFE_API_KEY": "jev-key",
    "ANTHROPIC_API_KEY": "llm-key",
}


def test_each_secret_goes_to_terraform_as_its_variable():
    assert deploy.secrets_env(ENV) == {
        "TF_VAR_snowflake_account": "MYORG-MY_ACCOUNT",
        "TF_VAR_snowflake_private_key_passphrase": "s3cret",
        "TF_VAR_twelve_data_api_key": "td-key",
        "TF_VAR_typesafe_api_key": "jev-key",
        "TF_VAR_anthropic_api_key": "llm-key",
    }


def test_a_missing_secret_is_named_and_no_value_is_shown():
    with pytest.raises(SetupError) as refused:
        deploy.secrets_env({**ENV, "TYPESAFE_API_KEY": " ", "ANTHROPIC_API_KEY": ""})

    message = str(refused.value)
    assert "TYPESAFE_API_KEY" in message and "ANTHROPIC_API_KEY" in message
    assert "s3cret" not in message


def test_the_plain_variables_name_the_commit_the_keys_folder_and_the_database(
    tmp_path,
):
    settings = Settings.from_env({**ENV, "SNOWFLAKE_LOCAL_DIR": str(tmp_path)})

    assert deploy.terraform_variables(settings, "abc1234", "TRADING_AGENT_TEST") == [
        "-var=image_tag=abc1234",
        f"-var=snowflake_keys_dir={(tmp_path / 'keys').as_posix()}",
        "-var=database=TRADING_AGENT_TEST",
    ]
    assert deploy.state_path(settings) == tmp_path / "kubernetes.tfstate"
