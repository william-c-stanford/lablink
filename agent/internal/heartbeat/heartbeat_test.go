package heartbeat

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"path/filepath"
	"strings"
	"sync/atomic"
	"testing"

	"github.com/william-c-stanford/lablink/agent/internal/queue"
)

// openTestQueue creates a queue in a temp dir for testing.
func openTestQueue(t *testing.T) *queue.Queue {
	t.Helper()
	dir := t.TempDir()
	q, err := queue.Open(filepath.Join(dir, "test.db"))
	if err != nil {
		t.Fatalf("opening queue: %v", err)
	}
	t.Cleanup(func() { q.Close() })
	return q
}

func TestHeartbeatSend(t *testing.T) {
	var received atomic.Bool
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		// Verify endpoint path contains agent ID.
		if !strings.Contains(r.URL.Path, "/agents/hb-agent-1/heartbeat") {
			t.Errorf("unexpected path: %s", r.URL.Path)
		}
		if r.Method != http.MethodPost {
			t.Errorf("unexpected method: %s", r.Method)
		}

		// Verify Authorization header.
		auth := r.Header.Get("Authorization")
		if auth != "Bearer hb-token" {
			t.Errorf("Authorization: got %q, want %q", auth, "Bearer hb-token")
		}

		// Verify User-Agent contains version.
		ua := r.Header.Get("User-Agent")
		if !strings.HasPrefix(ua, "lablink-agent/") {
			t.Errorf("User-Agent should start with lablink-agent/, got %q", ua)
		}

		// Parse the payload and verify fields.
		body, err := io.ReadAll(r.Body)
		if err != nil {
			t.Errorf("reading body: %v", err)
		}
		var payload map[string]interface{}
		if err := json.Unmarshal(body, &payload); err != nil {
			t.Errorf("unmarshalling payload: %v", err)
		}

		// Verify queue_depth is present.
		if _, ok := payload["queue_depth"]; !ok {
			t.Error("payload missing queue_depth")
		}

		// Verify version is present.
		if _, ok := payload["version"]; !ok {
			t.Error("payload missing version")
		}

		received.Store(true)
		w.WriteHeader(http.StatusOK)
	}))
	t.Cleanup(srv.Close)

	q := openTestQueue(t)
	hb := New(srv.URL, "hb-agent-1", "hb-token", "0.1.0", "")

	// Call the internal send method directly.
	hb.send(context.Background(), q)

	if !received.Load() {
		t.Error("server never received the heartbeat")
	}
}

func TestHeartbeatHandlesError(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
		w.Write([]byte(`{"errors":[{"code":"SERVER_ERROR","message":"down"}]}`))
	}))
	t.Cleanup(srv.Close)

	q := openTestQueue(t)
	hb := New(srv.URL, "hb-agent-1", "hb-token", "0.1.0", "")

	// Should not panic when server returns an error.
	hb.send(context.Background(), q)
}

func TestHeartbeatServerUnreachable(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {}))
	serverURL := srv.URL
	srv.Close()

	q := openTestQueue(t)
	hb := New(serverURL, "hb-agent-1", "hb-token", "0.1.0", "")

	// Should not panic when server is unreachable.
	hb.send(context.Background(), q)
}
