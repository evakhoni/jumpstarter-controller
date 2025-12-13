.PHONY: help build build-config-svc build-bootc push push-config-svc push-bootc

# Default image tags
CONFIG_SVC_IMG ?= quay.io/jumpstarter-dev/microshift/config-svc:latest
BOOTC_IMG ?= quay.io/jumpstarter-dev/microshift/bootc:latest


help: ## Display this help
	@awk 'BEGIN {FS = ":.*##"; printf "\nUsage:\n  make \033[36m<target>\033[0m\n"} /^[a-zA-Z_0-9-]+:.*?##/ { printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2 } /^##@/ { printf "\n\033[1m%s\033[0m\n", substr($$0, 5) } ' $(MAKEFILE_LIST)

##@ Build

build: build-config-svc ## Build config-svc container (default target)

build-config-svc: ## Build the config-svc container image
	@echo "Building config-svc container: $(CONFIG_SVC_IMG)"
	cd config-svc && podman build -t $(CONFIG_SVC_IMG) -f Containerfile .

build-bootc: ## Build the bootc image with MicroShift
	@echo "Building bootc image: $(BOOTC_IMG): buinding as root to be on the container storage from root"
	sudo podman build -t $(BOOTC_IMG) -f Containerfile ../..

output/qcow2/disk.qcow2: ## Build a bootable QCOW2 image from the bootc image
	@echo "Building QCOW2 image from: $(BOOTC_IMG)"
	@echo "Running bootc-image-builder..."
	@mkdir -p output
	sudo podman run \
		--rm \
		-it \
		--privileged \
		--pull=newer \
		--security-opt label=type:unconfined_t \
		-v ./config.toml:/config.toml:ro \
		-v ./output:/output \
		-v /var/lib/containers/storage:/var/lib/containers/storage \
		quay.io/centos-bootc/bootc-image-builder:latest \
		--type qcow2 \
		-v \
		$(BOOTC_IMG)
	@echo "QCOW2 image built successfully in ./output/"

##@ Push

push: push-config-svc ## Push config-svc container to registry

push-config-svc: ## Push the config-svc container image to registry
	@echo "Pushing config-svc container: $(CONFIG_SVC_IMG)"
	podman push $(CONFIG_SVC_IMG)

push-bootc: ## Push the bootc image to registry
	@echo "Pushing bootc image: $(BOOTC_IMG)"
	podman push $(BOOTC_IMG)

##@ Development

build-all: build-config-svc build-bootc ## Build both config-svc and bootc images

push-all: push-config-svc push-bootc ## Push both images to registry

clean: ## Clean up local images and build artifacts
	@echo "Removing local images..."
	-podman rmi $(CONFIG_SVC_IMG)
	-podman rmi $(BOOTC_IMG)
	@echo "Removing QCOW2 output..."
	-sudo rm -rf output/qcow2/disk.qcow2

