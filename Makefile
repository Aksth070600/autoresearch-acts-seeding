.DEFAULT_GOAL := help

ACTS_SOURCE ?= /storage/thomaaks/acts-v46.5.0
ACTS_BUILD_DIR ?= $(ACTS_SOURCE)/build
ACTS_VERSION ?= v46.5.0
ACTS_BUILD_JOBS ?= 8
ITK_EVENTS ?= 10
ITK_WORKLOAD ?= ttbar_pu200
ITK_THREADS ?= 1
ITK_SEED ?= 42
ITK_PILEUP ?= 200
ITK_STAGE ?= full
ITK_METRICS ?= none
EVOLUTION_PYTHON ?= /usr/bin/python3
REPORT_DATASET ?= development
REPORT_X_METRIC ?= timed_seeding_time_per_event_ms
REPORT_Y_METRIC ?= timed_ambiguity_particle_efficiency
HEPP_RUN_TIMEOUT ?= 1800
HEPP_HOST ?= thomaaks@hepp02.hpc.uio.no
HEPP_STORAGE ?= /storage/thomaaks
HEPP_FILES_REMOTE ?= $(HEPP_STORAGE)/HEPP-files
HEPP_TMUX_SESSION ?= acts-hepp02
HEPP_TMUX_TARGET ?= $(HEPP_TMUX_SESSION):0
HEPP_APPTAINER ?= /cvmfs/atlas.cern.ch/repo/containers/sw/apptainer/x86_64-el9/current/bin/apptainer
HEPP_CONTAINER_IMAGE ?= /cvmfs/atlas.cern.ch/repo/containers/images/singularity/x86_64-almalinux9.img
HEPP_CONTAINER_BINDS ?= -B /cvmfs -B /storage -B /home/aksth

.PHONY: help test setupActs setup build export-hepp-files hepp02-tmux-create hepp02-tmux-attach hepp02-tmux hepp02-tmux-status hepp02-setupActs hepp02-build hepp02-setup hepp02-setup-and-build hepp02-full-chain-itk evaluate report campaign-status evolve record select-evaluation evaluate-selected

help:
	@printf '%s\n' \
	  'make test      Run focused protocol and primary-objective tests.' \
	  'make setupActs  Configure ACTS v46.5.0 and its Python/example bindings.' \
	  'make build      Build the configured ACTS tree.' \
	  'make setup                    Verify the ACTS Python environment in this shell.' \
	  'make export-hepp-files       Copy HEPP-files to HEPP02 storage.' \
	  'make hepp02-tmux-create      Create the persistent ACTS tmux session.' \
	  'make hepp02-tmux-attach      Attach to the persistent ACTS tmux session.' \
	  'make hepp02-tmux             Create if needed, then attach to the session.' \
	  'make hepp02-tmux-status      Show the ACTS tmux session status.' \
	  'make hepp02-setupActs        Copy files and configure ACTS on HEPP02.' \
	  'make hepp02-build            Copy files and build ACTS on HEPP02.' \
	  'make hepp02-setup            Copy files and verify ACTS Python on HEPP02.' \
	  'make hepp02-setup-and-build  Copy files, configure, and build ACTS on HEPP02.' \
	  'make hepp02-full-chain-itk   Run the configurable ttbar ITk chain and return output.' \
	  '  Defaults use the v2 protocol: 10 events and one ACTS thread.' \
	  '  ITK_STAGE=seeding stops after seeding; full runs reconstruction.' \
	  '  ITK_METRICS=time adds GNU time RSS and CPU metrics; none runs clean.' \
	  'make evaluate CANDIDATE=name  Run 10-event development stages for a committed candidate.' \
	  'make report                 Build the results report and live campaign dashboard.' \
	  'make campaign-status        Generate campaign-status.json from records and live state.' \
	  'make evolve                 Select a protocol-compatible Pareto candidate.' \
	  'make record CANDIDATE=name  Print the latest candidate result and failure logs.' \
	  'make select-evaluation      Show Genesis plus four unique evaluation candidates.' \
	  'make evaluate-selected      Evaluate the selected candidates and rebuild the report.' \
	  '' \
	  'After local setup, use: source orchestration-files/HEPP-files/setup.sh' \
	  'Override HEPP_HOST, HEPP_STORAGE, or HEPP_TMUX_TARGET for another remote.'

test:
	/usr/bin/python3 -m unittest discover -s tests -v

setupActs:
	ACTS_SOURCE='$(ACTS_SOURCE)' ACTS_BUILD_DIR='$(ACTS_BUILD_DIR)' ACTS_VERSION='$(ACTS_VERSION)' ./orchestration-files/HEPP-files/setupActs.sh

build:
	ACTS_SOURCE='$(ACTS_SOURCE)' ACTS_BUILD_DIR='$(ACTS_BUILD_DIR)' ACTS_BUILD_JOBS='$(ACTS_BUILD_JOBS)' ./orchestration-files/HEPP-files/build.sh

setup:
	ACTS_SOURCE='$(ACTS_SOURCE)' ACTS_BUILD_DIR='$(ACTS_BUILD_DIR)' bash -lc 'source orchestration-files/HEPP-files/setup.sh'

export-hepp-files:
	ssh '$(HEPP_HOST)' "mkdir -p '$(HEPP_FILES_REMOTE)'"
	tar -C orchestration-files -cf - HEPP-files | ssh '$(HEPP_HOST)' "tar -C '$(HEPP_STORAGE)' -xf -"

hepp02-tmux-create:
	ssh '$(HEPP_HOST)' "if tmux has-session -t '$(HEPP_TMUX_SESSION)' 2>/dev/null; then printf '%s\\n' 'tmux session already exists: $(HEPP_TMUX_SESSION)'; else tmux new-session -d -s '$(HEPP_TMUX_SESSION)' '$(HEPP_APPTAINER) shell $(HEPP_CONTAINER_BINDS) $(HEPP_CONTAINER_IMAGE)'; printf '%s\\n' 'created tmux session: $(HEPP_TMUX_SESSION)'; fi"

hepp02-tmux-attach:
	ssh -t '$(HEPP_HOST)' "tmux attach-session -t '$(HEPP_TMUX_SESSION)'"

hepp02-tmux: hepp02-tmux-create
	$(MAKE) hepp02-tmux-attach

hepp02-tmux-status:
	ssh '$(HEPP_HOST)' "tmux has-session -t '$(HEPP_TMUX_SESSION)' 2>/dev/null && tmux list-windows -t '$(HEPP_TMUX_SESSION)' || printf '%s\\n' 'tmux session is not running: $(HEPP_TMUX_SESSION)'"

hepp02-setupActs: export-hepp-files hepp02-tmux-create
	ssh '$(HEPP_HOST)' "tmux has-session -t '$(HEPP_TMUX_TARGET)' && tmux send-keys -t '$(HEPP_TMUX_TARGET)' 'cd $(HEPP_STORAGE) && ACTS_SOURCE=$(ACTS_SOURCE) ACTS_BUILD_DIR=$(ACTS_BUILD_DIR) ACTS_VERSION=$(ACTS_VERSION) bash HEPP-files/setupActs.sh' C-m"
	@printf '%s\n' 'ACTS setup command sent to $(HEPP_TMUX_TARGET).'

hepp02-build: export-hepp-files hepp02-tmux-create
	ssh '$(HEPP_HOST)' "tmux has-session -t '$(HEPP_TMUX_TARGET)' && tmux send-keys -t '$(HEPP_TMUX_TARGET)' 'cd $(HEPP_STORAGE) && ACTS_SOURCE=$(ACTS_SOURCE) ACTS_BUILD_DIR=$(ACTS_BUILD_DIR) ACTS_BUILD_JOBS=$(ACTS_BUILD_JOBS) bash HEPP-files/build.sh' C-m"
	@printf '%s\n' 'ACTS build command sent to $(HEPP_TMUX_TARGET).'

hepp02-setup: export-hepp-files hepp02-tmux-create
	ssh '$(HEPP_HOST)' "tmux has-session -t '$(HEPP_TMUX_TARGET)' && tmux send-keys -t '$(HEPP_TMUX_TARGET)' 'cd $(HEPP_STORAGE) && ACTS_SOURCE=$(ACTS_SOURCE) ACTS_BUILD_DIR=$(ACTS_BUILD_DIR) bash -lc '\''source HEPP-files/setup.sh'\''' C-m"
	@printf '%s\n' 'ACTS setup verification command sent to $(HEPP_TMUX_TARGET).'

hepp02-setup-and-build: export-hepp-files hepp02-tmux-create
	ssh '$(HEPP_HOST)' "tmux has-session -t '$(HEPP_TMUX_TARGET)' && tmux send-keys -t '$(HEPP_TMUX_TARGET)' 'cd $(HEPP_STORAGE) && ACTS_SOURCE=$(ACTS_SOURCE) ACTS_BUILD_DIR=$(ACTS_BUILD_DIR) ACTS_VERSION=$(ACTS_VERSION) bash HEPP-files/setupActs.sh && ACTS_SOURCE=$(ACTS_SOURCE) ACTS_BUILD_DIR=$(ACTS_BUILD_DIR) ACTS_BUILD_JOBS=$(ACTS_BUILD_JOBS) bash HEPP-files/build.sh' C-m"
	@printf '%s\n' 'ACTS setup and build commands sent to $(HEPP_TMUX_TARGET).'

evaluate:
	@if [ -z "$(CANDIDATE)" ]; then echo 'usage: make evaluate CANDIDATE=name [EVALUATION=1]' >&2; exit 2; fi
	ACTS_BUILD_JOBS='$(ACTS_BUILD_JOBS)' python3 orchestration-files/evaluate.py "$(CANDIDATE)" $(if $(filter 1 true yes,$(EVALUATION)),--evaluation,)

report:
	python3 orchestration-files/report.py \
		--dataset '$(REPORT_DATASET)' \
		--x-metric '$(REPORT_X_METRIC)' \
		--y-metric '$(REPORT_Y_METRIC)' \
		--output reports/site

campaign-status:
	/usr/bin/python3 orchestration-files/campaign_status.py

evolve:
	$(EVOLUTION_PYTHON) orchestration-files/evolution.py --dataset development

record:
	@if [ -z "$(CANDIDATE)" ]; then echo 'usage: make record CANDIDATE=name [EVALUATION=1]' >&2; exit 2; fi
	$(EVOLUTION_PYTHON) orchestration-files/record.py "$(CANDIDATE)" $(if $(filter 1 true yes,$(EVALUATION)),--evaluation,)

select-evaluation:
	$(EVOLUTION_PYTHON) orchestration-files/select-evaluation.py --json

evaluate-selected:
	$(EVOLUTION_PYTHON) orchestration-files/evaluate-selected.py
	$(MAKE) report

hepp02-full-chain-itk: export-hepp-files hepp02-tmux-create
	@run_id=$$(date +%s); \
	start_marker="ACTS_FULL_CHAIN_ITK_START[$$run_id]"; \
	end_marker="ACTS_FULL_CHAIN_ITK_DONE[$$run_id]"; \
	ssh '$(HEPP_HOST)' "tmux has-session -t '$(HEPP_TMUX_TARGET)' && tmux send-keys -t '$(HEPP_TMUX_TARGET)' 'cd $(HEPP_STORAGE) && ACTS_SOURCE=$(ACTS_SOURCE) ACTS_BUILD_DIR=$(ACTS_BUILD_DIR) bash HEPP-files/run-full-chain-itk.sh $(ITK_EVENTS) $(ITK_WORKLOAD) $(ITK_THREADS) $(ITK_SEED) $(ITK_PILEUP) $(ITK_STAGE) $(ITK_METRICS) $$run_id' C-m"; \
	deadline=$$(($$(date +%s) + $(HEPP_RUN_TIMEOUT))); \
	captured=''; \
	done=0; \
	while [ "$$(date +%s)" -lt "$$deadline" ]; do \
		captured="$$(ssh '$(HEPP_HOST)' "tmux capture-pane -p -J -t '$(HEPP_TMUX_TARGET)' -S -" 2>/dev/null || true)"; \
		if printf '%s\\n' "$$captured" | grep -Fq "$$end_marker"; then done=1; break; fi; \
		sleep 2; \
	done; \
	if [ "$$done" -ne 1 ]; then echo "error: full_chain_itk.py timed out after $(HEPP_RUN_TIMEOUT)s" >&2; exit 1; fi; \
	printf '%s\\n' "$$captured" | awk -v start="$$start_marker" -v end="$$end_marker" 'index($$0, start) == 1 { inside=1; next } inside { if (index($$0, end) == 1) exit; print }'
