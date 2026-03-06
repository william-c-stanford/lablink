package config_test

import (
	"os"
	"path/filepath"
	"testing"

	"github.com/william-c-stanford/lablink/agent/internal/config"
)

func TestDefaultConfig(t *testing.T) {
	cfg := config.DefaultConfig()
	if cfg.APIURL == "" {
		t.Fatal("expected non-empty APIURL in default config")
	}
	if cfg.LogLevel == "" {
		t.Fatal("expected non-empty LogLevel in default config")
	}
	if cfg.APIURL != "https://app.lablink.io/api/v1" {
		t.Errorf("default APIURL: got %q, want %q", cfg.APIURL, "https://app.lablink.io/api/v1")
	}
}

func TestSaveAndLoad(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "agent.yaml")

	original := &config.Config{
		APIURL:     "https://test.lablink.io",
		AgentID:    "agent-abc",
		AgentToken: "tok-xyz",
		LogLevel:   "debug",
		ProxyURL:   "http://proxy.corp.com:8080",
		WatchedFolders: []config.WatchedFolder{
			{Path: "/tmp/instruments", Extensions: []string{".csv"}},
		},
	}

	if err := config.Save(original, path); err != nil {
		t.Fatalf("Save: %v", err)
	}

	if _, err := os.Stat(path); err != nil {
		t.Fatalf("config file not created: %v", err)
	}

	loaded, err := config.Load(path)
	if err != nil {
		t.Fatalf("Load: %v", err)
	}

	if loaded.APIURL != original.APIURL {
		t.Errorf("APIURL: got %q, want %q", loaded.APIURL, original.APIURL)
	}
	if loaded.AgentID != original.AgentID {
		t.Errorf("AgentID: got %q, want %q", loaded.AgentID, original.AgentID)
	}
	if loaded.AgentToken != original.AgentToken {
		t.Errorf("AgentToken: got %q, want %q", loaded.AgentToken, original.AgentToken)
	}
	if loaded.ProxyURL != original.ProxyURL {
		t.Errorf("ProxyURL: got %q, want %q", loaded.ProxyURL, original.ProxyURL)
	}
	if len(loaded.WatchedFolders) != 1 {
		t.Errorf("WatchedFolders: got %d, want 1", len(loaded.WatchedFolders))
	}
}

func TestIsRegistered(t *testing.T) {
	cfg := &config.Config{}
	if cfg.IsRegistered() {
		t.Error("empty config should not be registered")
	}
	cfg.AgentID = "x"
	if cfg.IsRegistered() {
		t.Error("config with only AgentID should not be registered")
	}
	cfg.AgentToken = "y"
	if !cfg.IsRegistered() {
		t.Error("config with AgentID+AgentToken should be registered")
	}
}

func TestConfigPath_Default(t *testing.T) {
	path, err := config.ConfigPath("")
	if err != nil {
		t.Fatalf("ConfigPath: %v", err)
	}
	if path == "" {
		t.Fatal("expected non-empty path")
	}
	if filepath.Base(path) != "agent.yaml" {
		t.Errorf("expected path to end with agent.yaml, got %q", path)
	}
}

func TestConfigPath_Explicit(t *testing.T) {
	path, err := config.ConfigPath("/custom/path/agent.yaml")
	if err != nil {
		t.Fatal(err)
	}
	if path != "/custom/path/agent.yaml" {
		t.Errorf("got %q, want /custom/path/agent.yaml", path)
	}
}

func TestLoad_MissingFile(t *testing.T) {
	cfg, err := config.Load("/nonexistent/path/agent.yaml")
	if err != nil {
		t.Fatalf("expected nil error for missing file, got: %v", err)
	}
	if cfg == nil {
		t.Fatal("expected default config for missing file")
	}
	if cfg.LogLevel != "info" {
		t.Errorf("default LogLevel: got %q, want %q", cfg.LogLevel, "info")
	}
}

func TestLoadConfig(t *testing.T) {
	t.Parallel()

	dir := t.TempDir()
	path := filepath.Join(dir, "agent.yaml")

	yamlContent := `api_url: https://lab.example.com
agent_id: agent-123
agent_token: secret-token-abc
log_level: debug
watched_folders:
  - path: /data/instruments
    extensions:
      - .csv
      - .tsv
  - path: /data/hplc
proxy_url: http://proxy.local:8080
`
	if err := os.WriteFile(path, []byte(yamlContent), 0o600); err != nil {
		t.Fatalf("writing temp yaml: %v", err)
	}

	cfg, err := config.Load(path)
	if err != nil {
		t.Fatalf("Load: %v", err)
	}

	if cfg.APIURL != "https://lab.example.com" {
		t.Errorf("APIURL: got %q, want %q", cfg.APIURL, "https://lab.example.com")
	}
	if cfg.AgentID != "agent-123" {
		t.Errorf("AgentID: got %q, want %q", cfg.AgentID, "agent-123")
	}
	if cfg.AgentToken != "secret-token-abc" {
		t.Errorf("AgentToken: got %q, want %q", cfg.AgentToken, "secret-token-abc")
	}
	if cfg.LogLevel != "debug" {
		t.Errorf("LogLevel: got %q, want %q", cfg.LogLevel, "debug")
	}
	if len(cfg.WatchedFolders) != 2 {
		t.Fatalf("WatchedFolders: got %d, want 2", len(cfg.WatchedFolders))
	}
	if cfg.WatchedFolders[0].Path != "/data/instruments" {
		t.Errorf("WatchedFolders[0].Path: got %q", cfg.WatchedFolders[0].Path)
	}
	if len(cfg.WatchedFolders[0].Extensions) != 2 {
		t.Errorf("WatchedFolders[0].Extensions: got %d, want 2", len(cfg.WatchedFolders[0].Extensions))
	}
	if cfg.ProxyURL != "http://proxy.local:8080" {
		t.Errorf("ProxyURL: got %q", cfg.ProxyURL)
	}
}

func TestSaveConfig(t *testing.T) {
	t.Parallel()

	dir := t.TempDir()
	path := filepath.Join(dir, "sub", "dir", "agent.yaml")

	original := &config.Config{
		APIURL:     "https://roundtrip.example.com",
		AgentID:    "rt-agent",
		AgentToken: "rt-token",
		LogLevel:   "warn",
		ProxyURL:   "http://p:3128",
		WatchedFolders: []config.WatchedFolder{
			{Path: "/instruments/hplc", Extensions: []string{".cdf", ".xml"}},
			{Path: "/instruments/pcr"},
		},
	}

	if err := config.Save(original, path); err != nil {
		t.Fatalf("Save: %v", err)
	}

	info, err := os.Stat(path)
	if err != nil {
		t.Fatalf("config file not created: %v", err)
	}
	if perm := info.Mode().Perm(); perm != 0o600 {
		t.Errorf("file permissions: got %o, want 600", perm)
	}

	loaded, err := config.Load(path)
	if err != nil {
		t.Fatalf("Load after Save: %v", err)
	}
	if loaded.APIURL != original.APIURL {
		t.Errorf("APIURL roundtrip: got %q, want %q", loaded.APIURL, original.APIURL)
	}
	if loaded.AgentID != original.AgentID {
		t.Errorf("AgentID roundtrip: got %q, want %q", loaded.AgentID, original.AgentID)
	}
	if loaded.AgentToken != original.AgentToken {
		t.Errorf("AgentToken roundtrip: got %q, want %q", loaded.AgentToken, original.AgentToken)
	}
	if len(loaded.WatchedFolders) != 2 {
		t.Fatalf("WatchedFolders roundtrip: got %d, want 2", len(loaded.WatchedFolders))
	}
	if loaded.ProxyURL != original.ProxyURL {
		t.Errorf("ProxyURL roundtrip: got %q, want %q", loaded.ProxyURL, original.ProxyURL)
	}
}

func TestDefaultExtensions(t *testing.T) {
	expected := map[string]bool{
		".csv": true, ".tsv": true, ".xml": true, ".json": true,
		".txt": true, ".rdml": true, ".eds": true, ".cdf": true,
	}

	if len(config.DefaultExtensions) != len(expected) {
		t.Fatalf("DefaultExtensions: got %d entries, want %d", len(config.DefaultExtensions), len(expected))
	}
	for _, ext := range config.DefaultExtensions {
		if !expected[ext] {
			t.Errorf("unexpected extension in DefaultExtensions: %q", ext)
		}
	}
}
