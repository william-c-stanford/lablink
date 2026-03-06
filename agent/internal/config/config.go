// Package config handles loading and saving the LabLink agent configuration.
package config

import (
	"fmt"
	"os"
	"path/filepath"

	"gopkg.in/yaml.v3"
)

const (
	DefaultConfigDir  = ".lablink"
	DefaultConfigName = "agent.yaml"
)

// WatchedFolder represents a directory to monitor for instrument output files.
type WatchedFolder struct {
	Path       string   `yaml:"path"`
	Extensions []string `yaml:"extensions,omitempty"`
}

// Config is the root configuration for the LabLink desktop agent.
type Config struct {
	APIURL         string          `yaml:"api_url"`
	AgentID        string          `yaml:"agent_id,omitempty"`
	AgentToken     string          `yaml:"agent_token,omitempty"`
	WatchedFolders []WatchedFolder `yaml:"watched_folders"`
	ProxyURL       string          `yaml:"proxy_url,omitempty"`
	LogLevel       string          `yaml:"log_level,omitempty"`
}

// DefaultExtensions is the whitelist of file extensions the agent will queue.
var DefaultExtensions = []string{
	".csv", ".tsv", ".xml", ".json", ".txt",
	".rdml", ".eds", ".cdf",
}

// DefaultConfig returns a Config with sensible defaults.
func DefaultConfig() *Config {
	return &Config{
		APIURL:         "https://app.lablink.io/api/v1",
		LogLevel:       "info",
		WatchedFolders: []WatchedFolder{},
	}
}

// ConfigPath returns the path to the agent config file, honouring an explicit
// path flag if provided, otherwise defaulting to ~/.lablink/agent.yaml.
func ConfigPath(explicit string) (string, error) {
	if explicit != "" {
		return explicit, nil
	}
	home, err := os.UserHomeDir()
	if err != nil {
		return "", fmt.Errorf("cannot determine home directory: %w", err)
	}
	return filepath.Join(home, DefaultConfigDir, DefaultConfigName), nil
}

// Load reads the config file at path (returning defaults if absent) and returns
// a populated *Config.
func Load(path string) (*Config, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		if os.IsNotExist(err) {
			return DefaultConfig(), nil
		}
		return nil, fmt.Errorf("reading config %s: %w", path, err)
	}

	var cfg Config
	if err := yaml.Unmarshal(data, &cfg); err != nil {
		return nil, fmt.Errorf("parsing config %s: %w", path, err)
	}
	return &cfg, nil
}

// Save writes cfg to path, creating parent directories as needed.
func Save(cfg *Config, path string) error {
	if err := os.MkdirAll(filepath.Dir(path), 0o700); err != nil {
		return fmt.Errorf("creating config dir: %w", err)
	}
	f, err := os.OpenFile(path, os.O_WRONLY|os.O_CREATE|os.O_TRUNC, 0o600)
	if err != nil {
		return fmt.Errorf("opening config file: %w", err)
	}
	defer f.Close()

	enc := yaml.NewEncoder(f)
	enc.SetIndent(2)
	if err := enc.Encode(cfg); err != nil {
		return fmt.Errorf("encoding config: %w", err)
	}
	return nil
}

// IsRegistered reports whether the agent has completed the registration flow.
func (c *Config) IsRegistered() bool {
	return c.AgentID != "" && c.AgentToken != ""
}
