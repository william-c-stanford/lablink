VERSION ?= $(shell git describe --tags --always --dirty 2>/dev/null || echo "dev")
LDFLAGS := -ldflags "-s -w -X github.com/william-c-stanford/lablink/agent/cmd.Version=$(VERSION)"
BINARY := lablink-agent
BUILD_DIR := bin

.PHONY: build test build-all clean

## build: compile the agent for the current platform
build:
	@mkdir -p $(BUILD_DIR)
	go build $(LDFLAGS) -o $(BUILD_DIR)/$(BINARY) .

## test: run all tests
test:
	go test ./...

## build-all: cross-compile for linux/amd64, darwin/arm64, windows/amd64
build-all:
	@mkdir -p $(BUILD_DIR)
	GOOS=linux   GOARCH=amd64 go build $(LDFLAGS) -o $(BUILD_DIR)/$(BINARY)-linux-amd64 .
	GOOS=darwin  GOARCH=arm64 go build $(LDFLAGS) -o $(BUILD_DIR)/$(BINARY)-darwin-arm64 .
	GOOS=windows GOARCH=amd64 go build $(LDFLAGS) -o $(BUILD_DIR)/$(BINARY)-windows-amd64.exe .

## clean: remove build artifacts
clean:
	rm -rf $(BUILD_DIR)
