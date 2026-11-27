"""Free tests for the kind deploy helper (infra/deploy.py): what it hands Terraform. No network,
no Terraform."""

import json

import pytest

from infra import deploy

ENV = {
    "TWELVE_DATA_API_KEY": "td-key",
    "TYPESAFE_API_KEY": "jev-key",
    "ANTHROPIC_API_KEY": "llm-key",
    "POSTGRES_HOST": "trading-agent.abc.ca-central-1.rds.amazonaws.com",
    "POSTGRES_API_PASSWORD": "pw-api",
    "POSTGRES_MEMORY_PASSWORD": "pw-memory",
    "POSTGRES_SIM_PASSWORD": "pw-sim",
    "POSTGRES_BUILDER_PASSWORD": "pw-builder",
    "POSTGRES_SETUP_PASSWORD": "pw-setup",
}


def test_each_secret_goes_to_terraform_as_its_variable():
    found = deploy.secrets_env(ENV)

    assert json.loads(found.pop("TF_VAR_postgres_passwords")) == {
        "api": "pw-api",
        "memory": "pw-memory",
        "sim": "pw-sim",
        "builder": "pw-builder",
    }
    assert found == {
        "TF_VAR_twelve_data_api_key": "td-key",
        "TF_VAR_typesafe_api_key": "jev-key",
        "TF_VAR_anthropic_api_key": "llm-key",
        "TF_VAR_postgres_host": "trading-agent.abc.ca-central-1.rds.amazonaws.com",
    }


def test_the_setup_login_stays_out_of_the_cluster():
    found = deploy.secrets_env(ENV)

    assert "pw-setup" not in json.dumps(found)


def test_port_and_encryption_go_along_when_set():
    found = deploy.secrets_env(
        {**ENV, "POSTGRES_PORT": "5433", "POSTGRES_SSL_MODE": "verify-full"}
    )

    assert found["TF_VAR_postgres_port"] == "5433"
    assert found["TF_VAR_postgres_ssl_mode"] == "verify-full"


def test_a_missing_secret_is_named_and_no_value_is_shown():
    with pytest.raises(deploy.SetupError) as refused:
        deploy.secrets_env(
            {**ENV, "TYPESAFE_API_KEY": " ", "POSTGRES_SIM_PASSWORD": ""}
        )

    message = str(refused.value)
    assert "TYPESAFE_API_KEY" in message and "POSTGRES_SIM_PASSWORD" in message
    assert "pw-api" not in message


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost"])
def test_an_address_of_this_computer_is_refused(host):
    with pytest.raises(deploy.SetupError, match="names the pod itself"):
        deploy.secrets_env({**ENV, "POSTGRES_HOST": host})


def test_the_plain_variables_name_the_commit_and_the_database():
    assert deploy.terraform_variables("abc1234", "TRADING_AGENT_TEST") == [
        "-var=image_tag=abc1234",
        "-var=database=TRADING_AGENT_TEST",
    ]
    assert deploy.state_path().name == "kubernetes.tfstate"
