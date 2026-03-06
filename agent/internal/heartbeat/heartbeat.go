// Package heartbeat sends periodic heartbeat signals to the LabLink backend,
// reporting the agent's status and queue depth.
package heartbeat

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"net/http"
	"net/url"
	"os"
	"path/filepath"
	"time"

	"github.com/william-c-stanford/lablink/agent/internal/config"
	"github.com/william-c-stanford/lablink/agent/internal/queue"
)

const defaultInterval = 60 * time.Second

// heartbeatPayload is the JSON body sent to the heartbeat endpoint.
type heartbeatPayload struct {
	QueueDepth    int    `json:"queue_depth"`
	UptimeSeconds int64  `json:"uptime_seconds"`
	Version       string `json:"version"`
}

// Heartbeat sends periodic POST requests to the backend.
type Heartbeat struct {
	baseURL    string
	agentID    string
	token      string
	version    string
	httpClient *http.Client
	startTime  time.Time
}

// New creates a Heartbeat.
func New(baseURL, agentID, token, version, proxyURL string) *Heartbeat {
	transport := &http.Transport{
		Proxy: http.ProxyFromEnvironment,
	}
	if proxyURL != "" {
		proxyParsed, err := url.Parse(proxyURL)
		if err == nil {
			transport.Proxy = http.ProxyURL(proxyParsed)
		}
	}
	return &Heartbeat{
		baseURL: baseURL,
		agentID: agentID,
		token:   token,
		version: version,
		httpClient: &http.Client{
			Timeout:   10 * time.Second,
			Transport: transport,
		},
		startTime: time.Now(),
	}
}

// Run starts the heartbeat loop, sending immediately then every 60 seconds.
// It blocks until ctx is cancelled.
func (h *Heartbeat) Run(ctx context.Context, q *queue.Queue) {
	h.send(ctx, q)
	ticker := time.NewTicker(defaultInterval)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			h.send(ctx, q)
		}
	}
}

func (h *Heartbeat) send(ctx context.Context, q *queue.Queue) {
	payload := heartbeatPayload{
		QueueDepth:    q.Depth(),
		UptimeSeconds: int64(time.Since(h.startTime).Seconds()),
		Version:       h.version,
	}
	body, _ := json.Marshal(payload)

	reqURL := fmt.Sprintf("%s/agents/%s/heartbeat", h.baseURL, h.agentID)
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, reqURL, bytes.NewReader(body))
	if err != nil {
		slog.Warn("heartbeat: failed to create request", "error", err)
		return
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Authorization", "Bearer "+h.token)
	req.Header.Set("User-Agent", "lablink-agent/"+h.version)

	resp, err := h.httpClient.Do(req)
	if err != nil {
		slog.Warn("heartbeat: send failed", "error", err)
		return
	}
	resp.Body.Close()

	if resp.StatusCode >= 400 {
		slog.Warn("heartbeat: server returned error", "status", resp.StatusCode)
		return
	}

	slog.Debug("heartbeat: sent", "queue_depth", payload.QueueDepth)

	// Record last heartbeat time for the status command.
	h.recordHeartbeatTime()
}

// recordHeartbeatTime writes the current time to a file for the status command.
func (h *Heartbeat) recordHeartbeatTime() {
	home, err := os.UserHomeDir()
	if err != nil {
		return
	}
	path := filepath.Join(home, config.DefaultConfigDir, "last_heartbeat")
	os.WriteFile(path, []byte(time.Now().Format(time.RFC3339)), 0o600)
}
