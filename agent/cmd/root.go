// Package cmd implements the Cobra CLI for the LabLink desktop agent.
package cmd

import (
	"fmt"
	"log/slog"
	"os"

	"github.com/spf13/cobra"
	"github.com/william-c-stanford/lablink/agent/internal/config"
)

var (
	cfgPath  string
	logLevel string
	cfg      *config.Config
)

// rootCmd is the base command. All subcommands are registered on it.
var rootCmd = &cobra.Command{
	Use:   "lablink-agent",
	Short: "LabLink desktop agent -- watches instrument directories and uploads data",
	Long: `lablink-agent is a lightweight daemon that monitors instrument output
directories and automatically uploads new files to the LabLink platform.

Run 'lablink-agent register' to connect this machine to your LabLink account,
then 'lablink-agent start' to begin watching directories.`,
	PersistentPreRunE: func(cmd *cobra.Command, args []string) error {
		// Skip config/logging setup for 'version' and 'help'.
		if cmd.Name() == "version" || cmd.Name() == "help" {
			return nil
		}
		return initConfig()
	},
	SilenceErrors: true,
	SilenceUsage:  true,
}

// Execute is the entry-point called by main.go.
func Execute() {
	if err := rootCmd.Execute(); err != nil {
		fmt.Fprintln(os.Stderr, "Error:", err)
		os.Exit(1)
	}
}

func init() {
	rootCmd.PersistentFlags().StringVar(&cfgPath, "config", "",
		"config file path (default: ~/.lablink/agent.yaml)")
	rootCmd.PersistentFlags().StringVar(&logLevel, "log-level", "",
		"log verbosity: debug|info|warn|error (overrides config)")

	rootCmd.AddCommand(startCmd)
	rootCmd.AddCommand(registerCmd)
	rootCmd.AddCommand(statusCmd)
	rootCmd.AddCommand(versionCmd)
}

// initConfig loads the config file and configures slog.
func initConfig() error {
	path, err := config.ConfigPath(cfgPath)
	if err != nil {
		return err
	}

	cfg, err = config.Load(path)
	if err != nil {
		return fmt.Errorf("loading config from %s: %w", path, err)
	}

	// Determine log level (flag > config > default "info").
	lvlStr := logLevel
	if lvlStr == "" {
		lvlStr = cfg.LogLevel
	}
	if lvlStr == "" {
		lvlStr = "info"
	}

	var level slog.Level
	switch lvlStr {
	case "debug":
		level = slog.LevelDebug
	case "warn":
		level = slog.LevelWarn
	case "error":
		level = slog.LevelError
	default:
		level = slog.LevelInfo
	}

	handler := slog.NewJSONHandler(os.Stderr, &slog.HandlerOptions{Level: level})
	slog.SetDefault(slog.New(handler))

	return nil
}
