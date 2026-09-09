.PHONY: artifact-preview artifact-public artifact-public-verify artifact-verify assets coda-open-assets coda-open-status cfp-status citation-check citation-check-online ecs-config-check ecs-host-nginx-check ecs-preflight ecs-runtime-backup ecs-runtime-restore-new-volume ecs-runtime-snapshot-smoke paper-assets paper-build-check paper-capture-check pilot-assets backend-sync backend-check capture-ui demo-latency demo-video demo-video-narrated dependency-audit dependency-license-audit image-vulnerability-audit e2e frontend-install frontend-check quality readiness-draft readiness-check rehearsal-check rehearsal-protocol rehearsal-surface shell-check pilot provider-browser-smoke provider-contract provider-smoke figures video-check \
	experiment-all experiment-community experiment-pilot experiment-transfer verify-results \
	heldout-download heldout-hash heldout-preflight heldout-unblind heldout-run heldout-score \
	paper-image pdf pdf-modern draft-check check clean compose-build compose-up compose-down

UV ?= uv
NPM ?= npm
PYTHON_VERSION ?= 3.10.20
PAPER_IMAGE ?= askdu-paper:texlive-2024
DEMO_LATENCY_REPETITIONS ?= 10
DEMO_LATENCY_INTERVAL ?= 2.05
DEMO_LATENCY_OUTPUT ?= experiments/results/demo-path-latency.json
VIDEO_CHECK_MODE ?= draft
VIDEO_MAX_SECONDS ?= 300
VIDEO_MAX_BYTES ?= 52428800
VIDEO_PATH ?= artifacts/demo/fallback-walkthrough.mp4
NARRATION_FILE ?=
NARRATED_VIDEO_OUTPUT ?= artifacts/demo/submission-walkthrough.mp4
DEPENDENCY_LICENSE_EVIDENCE ?= experiments/evidence/dependency-license-inventory-v0.4.0.json
ECS_ENV_FILE ?=
ECS_PUBLIC_ORIGIN ?=
ECS_INGRESS_MODE ?= host-nginx
ECS_HOST_NGINX_CONFIG ?=
ECS_HOST_NGINX_ARG = $(if $(strip $(ECS_HOST_NGINX_CONFIG)),--host-nginx-config "$(ECS_HOST_NGINX_CONFIG)")
RUNTIME_BACKUP_DIR ?=
RUNTIME_SNAPSHOT_ARCHIVE ?=
RUNTIME_SNAPSHOT_SHA256 ?=
RUNTIME_RESTORE_VOLUME ?=
REHEARSAL_RECORD ?=
PILOT_QUESTION := What are the Pearson correlation coefficients between the number of students who took the SHSAT and the percentage of Asian, Black/Hispanic, and White students for Grade 8 in 2016, using SHSAT registration and tester data that includes grade level information?

assets:
	./scripts/fetch_research_assets.sh --all

pilot-assets:
	./scripts/fetch_research_assets.sh --coda-pilots

coda-open-assets:
	$(UV) run --project backend python scripts/sync_coda_open_release.py --all-open

coda-open-status:
	$(UV) run --project backend python scripts/sync_coda_open_release.py --status

paper-assets:
	./scripts/fetch_paper_template.sh

artifact-preview:
	./scripts/build_artifact_bundle.sh --preview

artifact-public:
	./scripts/build_artifact_bundle.sh --public

artifact-public-verify: artifact-public
	./scripts/verify_artifact_bundle.sh \
		artifacts/release/ask-dont-upload-artifact-v0.4.0-release.tar.gz

artifact-verify: artifact-preview
	./scripts/verify_artifact_bundle.sh \
		artifacts/release/ask-dont-upload-artifact-v0.4.0-preview.tar.gz

dependency-audit:
	./scripts/audit_dependencies.sh

dependency-license-audit: compose-build
	$(UV) run --project backend python scripts/audit_dependency_licenses.py \
		--expected "$(DEPENDENCY_LICENSE_EVIDENCE)"

image-vulnerability-audit: compose-build
	./scripts/audit_container_images.sh

cfp-status: paper-assets
	$(UV) run --project backend python scripts/check_vldb2027_status.py

citation-check:
	$(UV) run --project backend python scripts/verify_paper_citations.py

citation-check-online:
	$(UV) run --project backend python scripts/verify_paper_citations.py --online

ecs-host-nginx-check:
	./scripts/check_host_nginx_syntax.sh

ecs-config-check: ecs-host-nginx-check
	$(UV) run --project backend python scripts/check_ecs_deployment.py \
		--env-file infra/ecs/production.env.example \
		--public-origin https://demo.example.com \
		--ingress-mode host-nginx \
		--host-nginx-config infra/ecs/host-nginx.conf.example \
		--allow-example-origin --skip-data-check

ecs-preflight:
	@test -n "$(ECS_ENV_FILE)" || (echo "Set ECS_ENV_FILE to the private deployment env path" >&2; exit 2)
	@test -n "$(ECS_PUBLIC_ORIGIN)" || (echo "Set ECS_PUBLIC_ORIGIN to the public HTTPS origin" >&2; exit 2)
	$(UV) run --project backend python scripts/check_ecs_deployment.py \
		--env-file "$(ECS_ENV_FILE)" \
		--public-origin "$(ECS_PUBLIC_ORIGIN)" \
		--ingress-mode "$(ECS_INGRESS_MODE)" $(ECS_HOST_NGINX_ARG)

ecs-runtime-backup:
	@test -n "$(ECS_ENV_FILE)" || (echo "Set ECS_ENV_FILE to the private deployment env path" >&2; exit 2)
	@test -n "$(RUNTIME_BACKUP_DIR)" || (echo "Set RUNTIME_BACKUP_DIR to a private directory outside the repository" >&2; exit 2)
	./scripts/backup_runtime_volume.sh \
		--env-file "$(ECS_ENV_FILE)" --output-dir "$(RUNTIME_BACKUP_DIR)"

ecs-runtime-restore-new-volume:
	@test -n "$(ECS_ENV_FILE)" || (echo "Set ECS_ENV_FILE to the private deployment env path" >&2; exit 2)
	@test -n "$(RUNTIME_SNAPSHOT_ARCHIVE)" || (echo "Set RUNTIME_SNAPSHOT_ARCHIVE to the private snapshot path" >&2; exit 2)
	@test -n "$(RUNTIME_SNAPSHOT_SHA256)" || (echo "Set RUNTIME_SNAPSHOT_SHA256 to its verified digest" >&2; exit 2)
	@test -n "$(RUNTIME_RESTORE_VOLUME)" || (echo "Set RUNTIME_RESTORE_VOLUME to a fresh Docker volume name" >&2; exit 2)
	./scripts/restore_runtime_volume.sh \
		--env-file "$(ECS_ENV_FILE)" \
		--archive "$(RUNTIME_SNAPSHOT_ARCHIVE)" \
		--expected-sha256 "$(RUNTIME_SNAPSHOT_SHA256)" \
		--new-volume-name "$(RUNTIME_RESTORE_VOLUME)"

ecs-runtime-snapshot-smoke: compose-build
	./scripts/smoke_runtime_snapshot.sh

backend-sync:
	$(UV) sync --frozen --project backend --python $(PYTHON_VERSION)

backend-check:
	$(UV) run --project backend ruff check scripts/audit_artifact_archive.py scripts/summarize_agentic_study.py
	$(UV) run --project backend ruff format --check scripts/audit_artifact_archive.py scripts/summarize_agentic_study.py
	$(UV) run --project backend ruff check backend/src backend/deployment backend/tests experiments scripts/audit_dependency_licenses.py scripts/audit_submission_readiness.py scripts/benchmark_demo_path.py scripts/check_demo_video.py scripts/check_ecs_deployment.py scripts/check_vldb2027_status.py scripts/mock_chat_provider.py scripts/mux_demo_narration.py scripts/render_system_figure.py scripts/runtime_snapshot.py scripts/sync_coda_open_release.py scripts/unblind_coda_heldout.py scripts/verify_demo_latency.py scripts/verify_paper_build.py scripts/verify_paper_capture.py scripts/verify_paper_citations.py scripts/verify_reported_results.py
	$(UV) run --project backend ruff format --check backend/src backend/deployment backend/tests experiments scripts/audit_dependency_licenses.py scripts/audit_submission_readiness.py scripts/benchmark_demo_path.py scripts/check_demo_video.py scripts/check_ecs_deployment.py scripts/check_vldb2027_status.py scripts/mock_chat_provider.py scripts/mux_demo_narration.py scripts/render_system_figure.py scripts/runtime_snapshot.py scripts/sync_coda_open_release.py scripts/unblind_coda_heldout.py scripts/verify_demo_latency.py scripts/verify_paper_build.py scripts/verify_paper_capture.py scripts/verify_paper_citations.py scripts/verify_reported_results.py
	$(UV) run --project backend mypy backend/src
	MYPYPATH=backend/src $(UV) run --project backend mypy backend/deployment
	$(UV) run --project backend pytest backend/tests -q

frontend-install:
	cd frontend && $(NPM) ci

frontend-check:
	node --test frontend/e2e/agentic-video-support.test.mjs
	cd frontend && $(NPM) run typecheck
	cd frontend && $(NPM) run build

shell-check:
	bash -n scripts/*.sh

quality: citation-check shell-check backend-check frontend-check

pilot:
	$(UV) run --project backend askdu run --question "$(PILOT_QUESTION)" \
		--output runtime/pilot-task-959.json

provider-contract:
	$(UV) run --project backend pytest backend/tests/test_llm.py backend/tests/test_provider_contract.py -q

provider-browser-smoke: compose-build
	@set -eu; \
		trap 'docker compose -f compose.yaml -f compose.model-smoke.yaml down' EXIT; \
		docker compose -f compose.yaml -f compose.model-smoke.yaml up -d --wait; \
		(cd frontend && $(NPM) run e2e:model-smoke)

provider-smoke:
	$(UV) run --project backend askdu provider-smoke

experiment-pilot:
	$(MAKE) experiment-community

experiment-community:
	$(UV) run --project backend python experiments/run_coda_community43_evaluation.py

experiment-transfer:
	$(UV) run --project backend python experiments/run_coda_community52_transfer.py

experiment-all: experiment-community experiment-transfer
	$(MAKE) verify-results

verify-results:
	$(UV) run --project backend python scripts/verify_reported_results.py
	$(UV) run --project backend python scripts/verify_demo_latency.py

heldout-download:
	./scripts/fetch_research_assets.sh --coda-heldout

heldout-hash:
	@./scripts/hash_evaluation_surface.sh

heldout-preflight:
	@test -n "$(HELDOUT_FREEZE_SHA256)" || (echo "Set HELDOUT_FREEZE_SHA256 to the recorded digest" >&2; exit 2)
	$(UV) run --project backend python scripts/unblind_coda_heldout.py \
		--preflight-only \
		--confirm-pre-unblinding-sha256 "$(HELDOUT_FREEZE_SHA256)"

heldout-unblind:
	@test -n "$(HELDOUT_FREEZE_SHA256)" || (echo "Set HELDOUT_FREEZE_SHA256 to the recorded digest" >&2; exit 2)
	$(UV) run --project backend python scripts/unblind_coda_heldout.py \
		--confirm-pre-unblinding-sha256 "$(HELDOUT_FREEZE_SHA256)"

heldout-run:
	$(UV) run --project backend python experiments/run_coda_heldout_v1.py

heldout-score:
	$(UV) run --project backend python experiments/score_coda_heldout_v1.py

figures:
	$(UV) run --project backend python scripts/render_system_figure.py

compose-build:
	docker compose build

compose-up:
	docker compose up -d

compose-down:
	docker compose down

e2e: compose-build
	@set -eu; \
		trap 'docker compose down' EXIT; \
		docker compose up -d --wait; \
		(cd frontend && $(NPM) run e2e)

capture-ui: compose-build
	@set -eu; \
		trap 'docker compose down' EXIT; \
		docker compose up -d --wait; \
	(cd frontend && $(NPM) run capture:paper)

.PHONY: capture-agentic-replay
capture-agentic-replay:
	node frontend/e2e/capture-agentic-replay.mjs
	$(UV) run --project backend python scripts/verify_paper_capture.py

# Read the already-running loopback agentic Web; never start/stop Compose or call a model.
.PHONY: demo-video-agentic
demo-video-agentic:
	node --test frontend/e2e/agentic-video-support.test.mjs
	node frontend/e2e/capture-agentic-video.mjs

paper-capture-check:
	$(UV) run --project backend python scripts/verify_paper_capture.py

paper-build-check:
	$(UV) run --project backend python scripts/verify_paper_build.py

demo-latency: compose-build
	@set -eu; \
		trap 'docker compose down' EXIT; \
		docker compose up -d --wait; \
		$(UV) run --project backend python scripts/benchmark_demo_path.py \
			--repetitions "$(DEMO_LATENCY_REPETITIONS)" \
			--interval-seconds "$(DEMO_LATENCY_INTERVAL)" \
			--output "$(DEMO_LATENCY_OUTPUT)"

demo-video: compose-build
	@set -eu; \
		command -v ffmpeg >/dev/null 2>&1 || { echo 'ffmpeg is required' >&2; exit 2; }; \
		trap 'docker compose down' EXIT; \
		docker compose up -d --wait; \
		(cd frontend && $(NPM) run capture:video); \
		ffmpeg -y -loglevel warning \
			-loop 1 -framerate 25 -t 5 -i artifacts/demo/storyboard/01-title.png \
			-loop 1 -framerate 25 -t 6 -i artifacts/demo/storyboard/02-ask.png \
			-loop 1 -framerate 25 -t 7 -i artifacts/demo/storyboard/03-execute.png \
			-loop 1 -framerate 25 -t 8 -i artifacts/demo/storyboard/04-discover.png \
			-loop 1 -framerate 25 -t 10 -i artifacts/demo/storyboard/05-repair.png \
			-loop 1 -framerate 25 -t 12 -i artifacts/demo/storyboard/06-verify.png \
			-loop 1 -framerate 25 -t 2 -i artifacts/demo/storyboard/07-transition.png \
			-loop 1 -framerate 25 -t 6 -i artifacts/demo/storyboard/08-challenge.png \
			-loop 1 -framerate 25 -t 8 -i artifacts/demo/storyboard/09-diagnosis.png \
			-loop 1 -framerate 25 -t 6 -i artifacts/demo/storyboard/10-close.png \
			-filter_complex \
			'[0:v][1:v][2:v][3:v][4:v][5:v][6:v][7:v][8:v][9:v]concat=n=10:v=1:a=0,format=yuv420p[outv]' \
			-map '[outv]' -an \
			-c:v libx264 -preset medium -crf 18 -g 50 \
			-movflags +faststart \
			-metadata title="Ask, Don't Upload — Captioned Stable-Frame Rehearsal Cut" \
			artifacts/demo/fallback-walkthrough.mp4; \
		$(MAKE) video-check

demo-video-narrated:
	@test -n "$(NARRATION_FILE)" || (echo "Set NARRATION_FILE to the author-recorded audio path" >&2; exit 2)
	$(UV) run --project backend python scripts/mux_demo_narration.py \
		--video artifacts/demo/fallback-walkthrough.mp4 \
		--narration "$(NARRATION_FILE)" \
		--output "$(NARRATED_VIDEO_OUTPUT)" \
		--max-seconds "$(VIDEO_MAX_SECONDS)" \
		--max-bytes "$(VIDEO_MAX_BYTES)"

video-check:
	$(UV) run --project backend python scripts/check_demo_video.py \
		--mode "$(VIDEO_CHECK_MODE)" \
		--max-seconds "$(VIDEO_MAX_SECONDS)" \
		--max-bytes "$(VIDEO_MAX_BYTES)" \
		"$(VIDEO_PATH)"

readiness-draft:
	$(UV) run --project backend python scripts/audit_submission_readiness.py --mode draft

readiness-check:
	$(UV) run --project backend python scripts/audit_submission_readiness.py --mode submission

rehearsal-surface:
	@$(UV) run --project backend python scripts/audit_submission_readiness.py \
		--print-demo-surface-sha256

rehearsal-protocol:
	@$(UV) run --project backend python scripts/audit_submission_readiness.py \
		--print-trial-protocol-sha256

rehearsal-check:
	@test -n "$(REHEARSAL_RECORD)" || (echo "Set REHEARSAL_RECORD to the real rehearsal JSON path" >&2; exit 2)
	$(UV) run --project backend python scripts/audit_submission_readiness.py \
		--trial-record "$(REHEARSAL_RECORD)"

pdf: paper-assets
	cd paper && latexmk -pdf -interaction=nonstopmode -halt-on-error main.tex

paper-image:
	docker build --file paper/Dockerfile --tag $(PAPER_IMAGE) paper

pdf-modern: paper-assets paper-image
	docker run --rm --network none --user "$$(id -u):$$(id -g)" \
		--volume "$(CURDIR)/paper:/work" $(PAPER_IMAGE)
	$(UV) run --project backend python scripts/verify_paper_build.py --write

draft-check: paper-assets paper-build-check paper-capture-check citation-check verify-results
	./scripts/check_submission.sh --draft
	$(MAKE) readiness-draft

check: paper-assets paper-build-check paper-capture-check citation-check verify-results
	@status=0; \
		./scripts/check_submission.sh --submission || status=1; \
		$(UV) run --project backend python scripts/audit_submission_readiness.py \
			--mode submission || status=1; \
		exit $$status

clean:
	cd paper && latexmk -C
	rm -f paper/main.build.json
