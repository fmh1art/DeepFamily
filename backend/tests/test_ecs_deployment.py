from __future__ import annotations

import importlib.util
import ipaddress
import sys
from pathlib import Path
from types import ModuleType

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def load_ecs_module() -> ModuleType:
    path = PROJECT_ROOT / "scripts/check_ecs_deployment.py"
    spec = importlib.util.spec_from_file_location("askdu_test_ecs_deployment", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load ECS deployment checker")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


ECS = load_ecs_module()


def test_production_env_is_private_and_outside_repository(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env_file = tmp_path / "askdu.env"
    env_file.write_text("ASKDU_PLANNER_MODE=registry\n", encoding="utf-8")

    with pytest.raises(ValueError, match="chmod 600"):
        ECS.validate_env_file_boundary(env_file, allow_example=False)

    env_file.chmod(0o600)
    ECS.validate_env_file_boundary(env_file, allow_example=False)

    monkeypatch.setattr(ECS, "PROJECT_ROOT", tmp_path)
    with pytest.raises(ValueError, match="outside the repository"):
        ECS.validate_env_file_boundary(env_file, allow_example=False)


def test_example_bypass_is_restricted_to_checked_template(tmp_path: Path) -> None:
    ECS.validate_env_file_boundary(ECS.CHECKED_EXAMPLE_ENV, allow_example=True)
    ECS.validate_diagnostic_flags(allow_example=True, skip_data_check=True)

    unrelated = tmp_path / "unrelated.env"
    unrelated.write_text("ASKDU_PLANNER_MODE=registry\n", encoding="utf-8")
    with pytest.raises(ValueError, match="restricted"):
        ECS.validate_env_file_boundary(unrelated, allow_example=True)
    with pytest.raises(ValueError, match="restricted"):
        ECS.validate_diagnostic_flags(allow_example=False, skip_data_check=True)


def test_public_origin_requires_standard_https() -> None:
    ECS.parse_public_origin("https://demo.askdu.test", allow_example=False)

    with pytest.raises(ValueError, match="HTTPS port 443"):
        ECS.parse_public_origin("https://demo.askdu.test:8443", allow_example=False)


def test_ingress_profiles_require_reachable_nonpublic_bindings() -> None:
    loopback = ipaddress.ip_address("127.0.0.1")
    private = ipaddress.ip_address("10.0.4.21")

    ECS.validate_ingress_binding(loopback, "host-nginx")
    ECS.validate_ingress_binding(private, "alb")

    with pytest.raises(ValueError, match="loopback"):
        ECS.validate_ingress_binding(private, "host-nginx")
    with pytest.raises(ValueError, match=r"specific .*private IP"):
        ECS.validate_ingress_binding(loopback, "alb")
    with pytest.raises(ValueError, match=r"specific .*private IP"):
        ECS.validate_ingress_binding(ipaddress.ip_address("192.0.2.1"), "alb")


def test_public_deployment_requires_bounded_run_retention() -> None:
    ECS.validate_run_retention({"ASKDU_RUN_RETENTION_HOURS": "24"})

    with pytest.raises(ValueError, match="between 1 and 720"):
        ECS.validate_run_retention({"ASKDU_RUN_RETENTION_HOURS": "0"})
    with pytest.raises(ValueError, match="must be an integer"):
        ECS.validate_run_retention({"ASKDU_RUN_RETENTION_HOURS": "one day"})


def test_model_backed_ecs_profile_is_exact_and_test_override_is_forbidden() -> None:
    profile = {
        "ASKDU_PLANNER_MODE": "agentic",
        "ASKDU_LLM_BASE_URL": (
            "https://aidp.bytedance.net/api/modelhub/online/v2/crawl?api-version=2024-03-01-preview"
        ),
        "ASKDU_LLM_MODEL": "gpt-5.5-2026-04-24",
        "ASKDU_LLM_API_KEY": "nonsecret-test-sentinel",
        "ASKDU_LLM_API_STYLE": "azure_chat",
        "ASKDU_LLM_AUTH_SCHEME": "api_key",
        "ASKDU_LLM_TOKEN_FIELD": "max_completion_tokens",
    }
    ECS.validate_model_configuration(profile)

    with pytest.raises(ValueError, match="project model"):
        ECS.validate_model_configuration({**profile, "ASKDU_LLM_MODEL": "other-model"})
    with pytest.raises(ValueError, match="test-provider override"):
        ECS.validate_model_configuration({**profile, "ASKDU_LLM_ALLOW_TEST_PROVIDER": "true"})


def test_host_nginx_template_preserves_client_ip_boundary() -> None:
    contents = ECS.HOST_NGINX_TEMPLATE.read_text(encoding="utf-8")
    ECS.validate_host_nginx_configuration(
        contents,
        public_hostname="demo.example.com",
        upstream_port=8080,
        allow_example=True,
    )

    production = contents.replace("demo.example.com", "demo.askdu.test")
    ECS.validate_host_nginx_configuration(
        production,
        public_hostname="demo.askdu.test",
        upstream_port=8080,
        allow_example=False,
    )

    unsafe = production.replace(
        "proxy_set_header X-Forwarded-For $remote_addr;",
        "proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;",
    )
    with pytest.raises(ValueError, match="overwrite untrusted"):
        ECS.validate_host_nginx_configuration(
            unsafe,
            public_hostname="demo.askdu.test",
            upstream_port=8080,
            allow_example=False,
        )


def test_systemd_template_stops_services_without_deleting_volumes() -> None:
    contents = ECS.SYSTEMD_TEMPLATE.read_text(encoding="utf-8")
    ECS.validate_systemd_template(contents)

    with pytest.raises(ValueError, match="preserve runtime"):
        ECS.validate_systemd_template(f"{contents}\nExecStopPost=/usr/bin/docker compose down -v\n")
