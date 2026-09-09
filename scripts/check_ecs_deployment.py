from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
import re
import stat
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any
from urllib.parse import SplitResult, urlsplit

PROJECT_ROOT = Path(__file__).resolve().parents[1]
COMPOSE_PATH = PROJECT_ROOT / "compose.yaml"
CHECKED_EXAMPLE_ENV = PROJECT_ROOT / "infra/ecs/production.env.example"
HOST_NGINX_TEMPLATE = PROJECT_ROOT / "infra/ecs/host-nginx.conf.example"
SYSTEMD_TEMPLATE = PROJECT_ROOT / "infra/ecs/askdu-compose.service.example"
PLACEHOLDER_SUFFIXES = (".example", ".example.com", ".example.net", ".example.org")
VPC_PRIVATE_NETWORKS = (
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("fc00::/7"),
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def path_is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def validate_env_file_boundary(env_file: Path, *, allow_example: bool) -> None:
    resolved = env_file.resolve()
    if allow_example:
        require(
            resolved == CHECKED_EXAMPLE_ENV.resolve(),
            "--allow-example-origin is restricted to the checked-in example env file",
        )
        return

    permissions = stat.S_IMODE(resolved.stat().st_mode)
    require(
        permissions & 0o077 == 0,
        "the production deployment env file must be chmod 600",
    )
    require(
        not path_is_within(resolved, PROJECT_ROOT),
        "the production deployment env file must live outside the repository",
    )


def validate_diagnostic_flags(*, allow_example: bool, skip_data_check: bool) -> None:
    require(
        not skip_data_check or allow_example,
        "--skip-data-check is restricted to the checked-in example configuration",
    )


def active_nginx_configuration(contents: str) -> str:
    return "\n".join(line.split("#", maxsplit=1)[0] for line in contents.splitlines())


def validate_host_nginx_configuration(
    contents: str,
    *,
    public_hostname: str,
    upstream_port: int,
    allow_example: bool,
) -> None:
    active = active_nginx_configuration(contents)
    server_names = {
        token.lower()
        for declaration in re.findall(r"(?m)^\s*server_name\s+([^;]+);", active)
        for token in declaration.split()
    }
    require(
        public_hostname in server_names,
        "host Nginx server_name does not include the public hostname",
    )
    require(
        re.search(r"(?m)^\s*listen\s+80(?:\s+default_server)?\s*;", active) is not None,
        "host Nginx must listen on port 80 for the HTTPS redirect",
    )
    require(
        re.search(r"(?m)^\s*listen\s+443\s+ssl(?:\s+http2)?\s*;", active) is not None,
        "host Nginx must terminate TLS on port 443",
    )
    require(
        "return 308 https://$host$request_uri;" in active,
        "host Nginx must redirect HTTP to HTTPS",
    )
    require(
        f"server 127.0.0.1:{upstream_port};" in active,
        "host Nginx upstream must match the loopback Compose port",
    )
    proxy_targets = re.findall(r"(?m)^\s*proxy_pass\s+([^;]+);", active)
    require(
        bool(proxy_targets) and set(proxy_targets) == {"http://askdu_web"},
        "host Nginx may proxy only to the checked loopback upstream",
    )
    require(
        "proxy_set_header X-Forwarded-For $remote_addr;" in active,
        "the outer proxy must overwrite untrusted X-Forwarded-For",
    )
    require(
        "$proxy_add_x_forwarded_for" not in active
        and "$http_x_forwarded_for" not in active,
        "the outer proxy must not append or trust a client-supplied forwarding chain",
    )
    require(
        "proxy_set_header X-Forwarded-Proto https;" in active,
        "host Nginx must mark the forwarded request as HTTPS",
    )
    require(
        "proxy_set_header Host $host;" in active,
        "host Nginx must preserve the validated public host",
    )
    require(
        re.search(
            r"limit_req_zone\s+\$binary_remote_addr\s+zone=askdu_outer_runs:",
            active,
        )
        is not None
        and "limit_req zone=askdu_outer_runs" in active,
        "host Nginx must rate-limit run creation by client IP",
    )
    require(
        re.search(
            r"limit_req_zone\s+\$binary_remote_addr\s+zone=askdu_outer_api:",
            active,
        )
        is not None
        and "limit_req zone=askdu_outer_api" in active,
        "host Nginx must rate-limit API traffic by client IP",
    )
    require(
        "client_max_body_size 16k;" in active,
        "host Nginx must retain the bounded request-body policy",
    )
    require(
        "real_ip_header" not in active and "set_real_ip_from" not in active,
        "the direct host proxy must not trust a forwarded client-IP header",
    )
    certificates = re.findall(r"(?m)^\s*ssl_certificate\s+([^;]+);", active)
    private_keys = re.findall(r"(?m)^\s*ssl_certificate_key\s+([^;]+);", active)
    require(
        len(certificates) == 1 and len(private_keys) == 1,
        "host Nginx must name exactly one TLS certificate and private key",
    )
    if not allow_example:
        require(
            not any(
                placeholder in active.lower()
                for placeholder in ("demo.example.com", "your-domain", "/path/to/")
            ),
            "replace host Nginx domain and certificate placeholders before deployment",
        )


def validate_systemd_template(contents: str) -> None:
    required = (
        "WorkingDirectory=/opt/askdu",
        "ExecStart=/usr/bin/docker compose --env-file /etc/askdu/askdu.env up -d --wait --remove-orphans",
        "ExecReload=/usr/bin/docker compose --env-file /etc/askdu/askdu.env up -d --wait --remove-orphans",
        "ExecStop=/usr/bin/docker compose --env-file /etc/askdu/askdu.env stop --timeout 30 web api",
    )
    for directive in required:
        require(directive in contents, f"systemd template is missing: {directive}")
    forbidden = (" down", "down -v", "volume rm", "system prune")
    require(
        not any(token in contents for token in forbidden),
        "systemd stop must preserve runtime and rollback volumes",
    )


def validate_checked_deployment_templates() -> None:
    require(HOST_NGINX_TEMPLATE.is_file(), "host Nginx template is missing")
    require(SYSTEMD_TEMPLATE.is_file(), "systemd Compose template is missing")
    validate_host_nginx_configuration(
        HOST_NGINX_TEMPLATE.read_text(encoding="utf-8"),
        public_hostname="demo.example.com",
        upstream_port=8080,
        allow_example=True,
    )
    validate_systemd_template(SYSTEMD_TEMPLATE.read_text(encoding="utf-8"))


def as_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise TypeError(f"{label} must be an object")
    return value


def as_sequence(value: Any, label: str) -> Sequence[Any]:
    if not isinstance(value, list):
        raise TypeError(f"{label} must be a list")
    return value


def validate_url_authority(parsed: SplitResult, label: str) -> str:
    hostname = parsed.hostname or ""
    require(bool(hostname), f"{label} must contain a hostname")
    require(
        not any(character.isspace() for character in hostname),
        f"{label} hostname is invalid",
    )
    try:
        _ = parsed.port
    except ValueError as exc:
        raise ValueError(f"{label} port is invalid") from exc
    return hostname.lower()


def validate_public_dns_name(hostname: str) -> None:
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        pass
    else:
        raise ValueError(
            "public origin must use the registered DNS name, not an IP address"
        )
    try:
        ascii_hostname = hostname.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise ValueError("public origin hostname is not valid IDNA") from exc
    labels = ascii_hostname.rstrip(".").split(".")
    require(len(labels) >= 2, "public origin must use a fully qualified DNS name")
    require(
        all(
            1 <= len(label) <= 63
            and re.fullmatch(
                r"[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?",
                label,
            )
            for label in labels
        ),
        "public origin hostname is invalid",
    )


def parse_public_origin(value: str, *, allow_example: bool) -> SplitResult:
    parsed = urlsplit(value)
    require(parsed.scheme == "https", "public origin must use HTTPS")
    hostname = validate_url_authority(parsed, "public origin")
    validate_public_dns_name(hostname)
    require(
        not parsed.username and not parsed.password,
        "public origin must not contain credentials",
    )
    require(
        parsed.port in {None, 443},
        "public origin must use the standard HTTPS port 443",
    )
    require(parsed.path in {"", "/"}, "public origin must not contain a path")
    require(
        not parsed.query and not parsed.fragment,
        "public origin must not contain query or fragment",
    )
    is_placeholder = hostname == "example.com" or hostname.endswith(
        PLACEHOLDER_SUFFIXES
    )
    require(
        allow_example or not is_placeholder,
        "replace the example public hostname before deployment",
    )
    return parsed


def normalize_origin(value: str) -> str:
    parsed = urlsplit(value.strip())
    require(parsed.scheme in {"http", "https"}, f"invalid CORS origin: {value!r}")
    validate_url_authority(parsed, "CORS origin")
    require(
        not parsed.username and not parsed.password,
        "CORS origins must not contain credentials",
    )
    require(parsed.path in {"", "/"}, "CORS origins must not contain a path")
    require(
        not parsed.query and not parsed.fragment,
        "CORS origins must not contain query or fragment",
    )
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}"


def trusted_host_matches(hostname: str, candidate: str) -> bool:
    candidate = candidate.strip().lower()
    if candidate == hostname:
        return True
    return candidate.startswith("*.") and hostname.endswith(candidate[1:])


def validate_bind_address(value: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
    try:
        address = ipaddress.ip_address(value)
    except ValueError as exc:
        raise ValueError(
            "ASKDU_BIND_ADDRESS must be a loopback or specific private IP"
        ) from exc
    require(
        not address.is_unspecified,
        "public wildcard binding is forbidden by the ECS topology",
    )
    require(not address.is_multicast, "multicast binding is invalid")
    require(not address.is_link_local, "link-local binding is invalid")
    require(
        address.is_loopback or address.is_private,
        "bind address must be loopback or private",
    )
    return address


def validate_ingress_binding(
    address: ipaddress.IPv4Address | ipaddress.IPv6Address,
    ingress_mode: str,
) -> None:
    require(
        ingress_mode in {"host-nginx", "alb"},
        "ingress mode must be host-nginx or alb",
    )
    if ingress_mode == "host-nginx":
        require(
            address.is_loopback,
            "host-nginx mode requires a loopback Compose binding",
        )
        return
    require(
        not address.is_loopback
        and any(
            address.version == network.version and address in network
            for network in VPC_PRIVATE_NETWORKS
        ),
        "ALB mode requires the ECS instance's specific RFC1918/ULA private IP",
    )


def render_compose(env_file: Path) -> Mapping[str, Any]:
    clean_environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("ASKDU_") and not key.startswith("COMPOSE_")
    }
    command = [
        "docker",
        "compose",
        "--project-name",
        "askdu-preflight",
        "--project-directory",
        str(PROJECT_ROOT),
        "--env-file",
        str(env_file),
        "--file",
        str(COMPOSE_PATH),
        "config",
        "--format",
        "json",
    ]
    try:
        completed = subprocess.run(
            command,
            cwd=PROJECT_ROOT,
            env=clean_environment,
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("Docker Compose is required for ECS preflight") from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            "Docker Compose could not render the production configuration"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("Docker Compose configuration timed out") from exc
    return as_mapping(json.loads(completed.stdout), "rendered Compose configuration")


def validate_service_security(name: str, service: Mapping[str, Any]) -> None:
    require(
        service.get("read_only") is True, f"{name} root filesystem must be read-only"
    )
    require(service.get("privileged") is not True, f"{name} must not be privileged")
    cap_drop = as_sequence(service.get("cap_drop"), f"{name}.cap_drop")
    require("ALL" in cap_drop, f"{name} must drop all Linux capabilities")
    security_options = as_sequence(service.get("security_opt"), f"{name}.security_opt")
    require(
        "no-new-privileges:true" in security_options,
        f"{name} must enable no-new-privileges",
    )
    require(service.get("init") is True, f"{name} must use an init process")
    require(
        service.get("restart") == "unless-stopped", f"{name} restart policy drifted"
    )
    pids_limit = service.get("pids_limit")
    require(
        isinstance(pids_limit, int) and 1 <= pids_limit <= 1024,
        f"{name} needs a bounded PID limit",
    )
    logging = as_mapping(service.get("logging"), f"{name}.logging")
    require(logging.get("driver") == "json-file", f"{name} logging driver drifted")
    options = as_mapping(logging.get("options"), f"{name}.logging.options")
    require(
        bool(options.get("max-size")) and bool(options.get("max-file")),
        f"{name} logs must rotate",
    )


def find_volume(service: Mapping[str, Any], target: str) -> Mapping[str, Any]:
    volumes = as_sequence(service.get("volumes"), "service.volumes")
    matching = [
        as_mapping(volume, "service volume")
        for volume in volumes
        if isinstance(volume, dict) and volume.get("target") == target
    ]
    require(len(matching) == 1, f"expected exactly one {target} mount")
    return matching[0]


def validate_model_configuration(api_environment: Mapping[str, Any]) -> None:
    planner_mode = str(api_environment.get("ASKDU_PLANNER_MODE", ""))
    require(
        planner_mode in {"registry", "model", "agentic"},
        "ASKDU_PLANNER_MODE is invalid",
    )
    if planner_mode == "registry":
        return

    allow_test_provider = (
        str(api_environment.get("ASKDU_LLM_ALLOW_TEST_PROVIDER", "false"))
        .strip()
        .lower()
    )
    require(
        allow_test_provider not in {"1", "true", "yes", "on"},
        "production must not enable the loopback test-provider override",
    )

    endpoint = str(api_environment.get("ASKDU_LLM_BASE_URL", "")).strip()
    model = str(api_environment.get("ASKDU_LLM_MODEL", "")).strip()
    credential = str(api_environment.get("ASKDU_LLM_API_KEY", "")).strip()
    require(
        endpoint and model and credential,
        "model mode requires endpoint, model, and a rotated key",
    )
    parsed = urlsplit(endpoint)
    endpoint_hostname = validate_url_authority(parsed, "model endpoint")
    require(
        parsed.scheme == "https" and bool(endpoint_hostname),
        "model endpoint must be an HTTPS URL",
    )
    require(
        not parsed.username and not parsed.password,
        "model endpoint must not embed credentials",
    )
    style = str(api_environment.get("ASKDU_LLM_API_STYLE", ""))
    require(
        style in {"azure_chat", "openai_base_url", "direct_chat_completions"},
        "model API style is invalid",
    )
    if style == "openai_base_url":
        require(
            not parsed.query and not parsed.fragment,
            "OpenAI base URL must not have query or fragment",
        )
    require("your-" not in model.lower(), "replace the placeholder model name")
    require("your-" not in credential.lower(), "replace the placeholder model key")
    require(
        endpoint == "https://aidp.bytedance.net/api/modelhub/online/v2/crawl"
        "?api-version=2024-03-01-preview",
        "model-backed deployment must use the project ModelHub endpoint",
    )
    require(
        model == "gpt-5.5-2026-04-24",
        "model-backed deployment must use the project model",
    )
    require(
        style == "azure_chat"
        and str(api_environment.get("ASKDU_LLM_AUTH_SCHEME", "")) == "api_key"
        and str(api_environment.get("ASKDU_LLM_TOKEN_FIELD", ""))
        == "max_completion_tokens",
        "model-backed deployment provider contract drifted",
    )


def validate_run_retention(api_environment: Mapping[str, Any]) -> None:
    raw = str(api_environment.get("ASKDU_RUN_RETENTION_HOURS", "")).strip()
    require(
        re.fullmatch(r"[0-9]+", raw) is not None,
        "ASKDU_RUN_RETENTION_HOURS must be an integer",
    )
    hours = int(raw)
    require(
        1 <= hours <= 720,
        "public ECS deployment requires run retention between 1 and 720 hours",
    )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_public_data(data_root: Path, environment_id: str) -> int:
    match = re.fullmatch(r"coda-community-(\d+)", environment_id)
    require(match is not None, "ECS preflight only supports a pinned CoDA community")
    community_id = match.group(1)
    manifest = (
        PROJECT_ROOT
        / "data"
        / "manifests"
        / f"coda-community-{community_id}-csv.sha256"
    )
    require(
        manifest.is_file(), f"missing source-integrity manifest for {environment_id}"
    )
    require(data_root.is_dir(), "download the public pilot data before ECS deployment")

    prefix = f"communities/community_{community_id}/full_community/"
    expected: dict[str, str] = {}
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        digest, relative = line.split(maxsplit=1)
        require(relative.startswith(prefix), "source-integrity manifest prefix drifted")
        local_relative = relative.removeprefix(prefix)
        require(
            local_relative not in expected,
            f"duplicate source manifest path: {local_relative}",
        )
        expected[local_relative] = digest

    actual = {
        path.relative_to(data_root).as_posix()
        for path in data_root.rglob("*.csv")
        if path.is_file()
    }
    require(
        actual == set(expected),
        "mounted CSV census differs from the pinned source manifest",
    )
    for relative, expected_digest in expected.items():
        require(
            sha256(data_root / relative) == expected_digest,
            f"source digest mismatch: {relative}",
        )
    return len(expected)


def validate_compose(
    rendered: Mapping[str, Any],
    *,
    public_origin: str,
    public_hostname: str,
    ingress_mode: str,
    skip_data_check: bool,
) -> tuple[int | None, str, int]:
    services = as_mapping(rendered.get("services"), "services")
    require(
        set(services) == {"api", "web"},
        "production Compose must contain only api and web",
    )
    api = as_mapping(services["api"], "services.api")
    web = as_mapping(services["web"], "services.web")
    validate_service_security("api", api)
    validate_service_security("web", web)

    require(not api.get("ports"), "API must not publish a host port")
    ports = as_sequence(web.get("ports"), "web.ports")
    require(len(ports) == 1, "Web must publish exactly one host port")
    port = as_mapping(ports[0], "web.ports[0]")
    bind_address = str(port.get("host_ip", ""))
    parsed_bind_address = validate_bind_address(bind_address)
    validate_ingress_binding(parsed_bind_address, ingress_mode)
    require(
        port.get("target") == 8080 and port.get("protocol") == "tcp",
        "Web target port drifted",
    )
    published = str(port.get("published", ""))
    require(
        published.isdigit() and 1 <= int(published) <= 65535,
        "published Web port is invalid",
    )
    published_port = int(published)

    api_environment = as_mapping(api.get("environment"), "api.environment")
    validate_run_retention(api_environment)
    trusted_hosts = [
        host.strip().lower()
        for host in str(api_environment.get("ASKDU_TRUSTED_HOSTS", "")).split(",")
        if host.strip()
    ]
    require(trusted_hosts, "ASKDU_TRUSTED_HOSTS must not be empty")
    require("*" not in trusted_hosts, "wildcard trusted hosts are forbidden")
    require(
        any(trusted_host_matches(public_hostname, host) for host in trusted_hosts),
        "public hostname is missing from ASKDU_TRUSTED_HOSTS",
    )
    cors_origins = {
        normalize_origin(origin)
        for origin in str(api_environment.get("ASKDU_CORS_ORIGINS", "")).split(",")
        if origin.strip()
    }
    require(
        public_origin in cors_origins,
        "public origin is missing from ASKDU_CORS_ORIGINS",
    )

    data_volume = find_volume(api, "/data/environment")
    require(data_volume.get("type") == "bind", "data environment must be a bind mount")
    require(data_volume.get("read_only") is True, "data environment must be read-only")
    runtime_volume = find_volume(api, "/runtime")
    require(
        runtime_volume.get("type") == "volume", "runtime state must use a named volume"
    )
    require(
        runtime_volume.get("read_only") is not True,
        "runtime state must remain writable",
    )
    declared_volumes = as_mapping(rendered.get("volumes"), "volumes")
    require(
        runtime_volume.get("source") in declared_volumes,
        "runtime named volume is undeclared",
    )
    runtime_definition = as_mapping(
        declared_volumes[runtime_volume["source"]], "runtime volume definition"
    )
    runtime_name = runtime_definition.get("name")
    require(
        isinstance(runtime_name, str)
        and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", runtime_name) is not None,
        "runtime volume must have an explicit safe name",
    )

    depends_on = as_mapping(web.get("depends_on"), "web.depends_on")
    api_dependency = as_mapping(depends_on.get("api"), "web.depends_on.api")
    require(
        api_dependency.get("condition") == "service_healthy",
        "Web must wait for API health",
    )
    web_environment = as_mapping(web.get("environment", {}), "web.environment")
    require(
        "ASKDU_LLM_API_KEY" not in web_environment,
        "model credential leaked into Web service",
    )

    if skip_data_check:
        return None, bind_address, published_port
    data_root = Path(str(data_volume.get("source", "")))
    environment_id = str(api_environment.get("ASKDU_ENVIRONMENT_ID", ""))
    return (
        validate_public_data(data_root, environment_id),
        bind_address,
        published_port,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate the rendered single-ECS deployment without printing secrets."
    )
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--public-origin", required=True)
    parser.add_argument(
        "--ingress-mode",
        choices=("host-nginx", "alb"),
        default="host-nginx",
    )
    parser.add_argument("--host-nginx-config", type=Path)
    parser.add_argument("--allow-example-origin", action="store_true")
    parser.add_argument("--skip-data-check", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    validate_diagnostic_flags(
        allow_example=args.allow_example_origin,
        skip_data_check=args.skip_data_check,
    )
    env_file = args.env_file.expanduser().resolve()
    require(env_file.is_file(), f"deployment env file does not exist: {env_file}")
    validate_env_file_boundary(env_file, allow_example=args.allow_example_origin)
    validate_checked_deployment_templates()
    parsed_origin = parse_public_origin(
        args.public_origin.strip(),
        allow_example=args.allow_example_origin,
    )
    public_origin = normalize_origin(args.public_origin)
    public_hostname = (parsed_origin.hostname or "").lower()
    rendered = render_compose(env_file)
    services = as_mapping(rendered.get("services"), "services")
    api = as_mapping(services.get("api"), "services.api")
    api_environment = as_mapping(api.get("environment"), "api.environment")
    validate_model_configuration(api_environment)
    verified_assets, bind_address, published_port = validate_compose(
        rendered,
        public_origin=public_origin,
        public_hostname=public_hostname,
        ingress_mode=args.ingress_mode,
        skip_data_check=args.skip_data_check,
    )

    if args.ingress_mode == "host-nginx":
        require(
            args.host_nginx_config is not None,
            "host-nginx mode requires --host-nginx-config",
        )
        host_nginx_config = args.host_nginx_config.expanduser().resolve()
        require(
            host_nginx_config.is_file(),
            f"host Nginx configuration does not exist: {host_nginx_config}",
        )
        if args.allow_example_origin:
            require(
                host_nginx_config == HOST_NGINX_TEMPLATE.resolve(),
                "example mode is restricted to the checked-in host Nginx template",
            )
        else:
            require(
                not path_is_within(host_nginx_config, PROJECT_ROOT),
                "the production host Nginx configuration must live outside the repository",
            )
        validate_host_nginx_configuration(
            host_nginx_config.read_text(encoding="utf-8"),
            public_hostname=public_hostname,
            upstream_port=published_port,
            allow_example=args.allow_example_origin,
        )
    else:
        require(
            args.host_nginx_config is None,
            "ALB mode must not supply a host Nginx configuration",
        )

    print(f"PASS: public origin and trusted-host boundary agree for {public_origin}.")
    if args.ingress_mode == "host-nginx":
        print(
            "PASS: host Nginx configuration declares TLS and proxies to "
            f"{bind_address}:{published_port}."
        )
    else:
        print(
            f"PASS: ALB profile binds Web to the specific private address {bind_address}:{published_port}."
        )
    print(
        "PASS: both services retain read-only roots, dropped capabilities, PID limits, and log rotation."
    )
    print(
        "PASS: source data is read-only and runtime state uses a switchable named volume."
    )
    if verified_assets is None:
        print(
            "INFO: source-byte verification was intentionally skipped for the example configuration."
        )
    else:
        print(
            f"PASS: {verified_assets} mounted CSV assets match the pinned SHA-256 manifest."
        )


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: ECS deployment preflight failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from None
