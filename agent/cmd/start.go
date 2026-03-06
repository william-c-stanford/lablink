package cmd

import (
	"context"
	"fmt"
	"log/slog"
	"os"
	"os/signal"
	"path/filepath"
	"syscall"
	"time"

	"github.com/spf13/cobra"
	"github.com/william-c-stanford/lablink/agent/internal/config"
	"github.com/william-c-stanford/lablink/agent/internal/heartbeat"
	"github.com/william-c-stanford/lablink/agent/internal/queue"
	"github.com/william-c-stanford/lablink/agent/internal/updater"
	"github.com/william-c-stanford/lablink/agent/internal/uploader"
	"github.com/william-c-stanford/lablink/agent/internal/watcher"
)

// Version is set at build time via ldflags.
var Version = "0.1.0"

var startCmd = &cobra.Command{
	Use:   "start",
	Short: "Start the agent daemon (watch directories and upload files)",
	Long: `Start starts the LabLink agent. It watches all directories configured in
~/.lablink/agent.yaml, queues new instrument output files, and uploads them to
the LabLink platform with automatic retry.

The agent must be registered first ('lablink-agent register').`,
	RunE: runStart,
}

func runStart(cmd *cobra.Command, args []string) error {
	if !cfg.IsRegistered() {
		return fmt.Errorf(
			"agent is not registered -- run 'lablink-agent register' first")
	}

	if len(cfg.WatchedFolders) == 0 {
		slog.Warn("no watched_folders configured -- add paths to ~/.lablink/agent.yaml")
	}

	slog.Info("lablink-agent starting",
		"version", Version,
		"api_url", cfg.APIURL,
		"agent_id", cfg.AgentID,
	)

	// Open the persistent queue.
	home, _ := os.UserHomeDir()
	dbPath := filepath.Join(home, config.DefaultConfigDir, "queue.db")
	if err := os.MkdirAll(filepath.Dir(dbPath), 0o700); err != nil {
		return fmt.Errorf("creating queue dir: %w", err)
	}
	q, err := queue.Open(dbPath)
	if err != nil {
		return fmt.Errorf("opening queue: %w", err)
	}
	defer q.Close()

	// Create the file watcher.
	fileCh := make(chan string, 100)
	w, err := watcher.New(cfg.WatchedFolders, fileCh)
	if err != nil {
		return fmt.Errorf("creating watcher: %w", err)
	}

	ctx, cancel := signal.NotifyContext(context.Background(),
		os.Interrupt, syscall.SIGTERM)
	defer cancel()

	// Start watching directories.
	if err := w.Start(); err != nil {
		return fmt.Errorf("starting watcher: %w", err)
	}
	defer w.Stop()

	// Start heartbeat goroutine.
	hb := heartbeat.New(cfg.APIURL, cfg.AgentID, cfg.AgentToken, Version, cfg.ProxyURL)
	go hb.Run(ctx, q)

	// Start auto-update checker.
	upd := updater.New(Version)
	go upd.Run(ctx)

	// Start upload worker goroutine: reads from fileCh, enqueues, and processes.
	ul := uploader.New(cfg.APIURL, cfg.AgentID, cfg.AgentToken, cfg.ProxyURL)
	go enqueueLoop(ctx, fileCh, q)
	go uploadLoop(ctx, q, ul)

	slog.Info("agent started -- press Ctrl+C to stop")
	<-ctx.Done()
	slog.Info("agent shutting down")
	return nil
}

// enqueueLoop reads stable file paths from the watcher channel and adds them
// to the persistent queue.
func enqueueLoop(ctx context.Context, fileCh <-chan string, q *queue.Queue) {
	for {
		select {
		case <-ctx.Done():
			return
		case path, ok := <-fileCh:
			if !ok {
				return
			}
			item := &queue.Item{FilePath: path}
			if err := q.Enqueue(item); err != nil {
				slog.Error("failed to enqueue file", "file", path, "error", err)
			} else {
				slog.Info("file queued for upload", "file", path)
			}
		}
	}
}

// uploadLoop polls the queue and uploads files with retry.
func uploadLoop(ctx context.Context, q *queue.Queue, ul *uploader.Uploader) {
	ticker := time.NewTicker(2 * time.Second)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			items, err := q.Dequeue(5)
			if err != nil {
				slog.Error("dequeue error", "error", err)
				continue
			}
			for _, item := range items {
				if err := ul.Upload(ctx, item.FilePath); err != nil {
					slog.Warn("upload failed",
						"file", item.FilePath,
						"retry", item.RetryCount,
						"error", err,
					)
					if nackErr := q.Nack(item.ID, err.Error()); nackErr != nil {
						slog.Error("nack failed", "error", nackErr)
					}
				} else {
					slog.Info("upload succeeded", "file", item.FilePath)
					if ackErr := q.Ack(item.ID); ackErr != nil {
						slog.Error("ack failed", "error", ackErr)
					}
				}
			}
		}
	}
}
