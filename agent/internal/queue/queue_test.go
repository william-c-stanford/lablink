package queue_test

import (
	"path/filepath"
	"testing"

	"github.com/william-c-stanford/lablink/agent/internal/queue"
)

func openQueue(t *testing.T) *queue.Queue {
	t.Helper()
	dir := t.TempDir()
	q, err := queue.Open(filepath.Join(dir, "test.db"))
	if err != nil {
		t.Fatalf("Open: %v", err)
	}
	t.Cleanup(func() { q.Close() })
	return q
}

func TestEnqueueDequeue(t *testing.T) {
	q := openQueue(t)

	if d := q.Depth(); d != 0 {
		t.Fatalf("expected depth 0, got %d", d)
	}

	item := &queue.Item{FilePath: "/tmp/data.csv"}
	if err := q.Enqueue(item); err != nil {
		t.Fatalf("Enqueue: %v", err)
	}
	if d := q.Depth(); d != 1 {
		t.Fatalf("expected depth 1, got %d", d)
	}

	items, err := q.Dequeue(10)
	if err != nil {
		t.Fatalf("Dequeue: %v", err)
	}
	if len(items) != 1 {
		t.Fatalf("expected 1 item, got %d", len(items))
	}
	if items[0].FilePath != "/tmp/data.csv" {
		t.Errorf("FilePath: got %q, want %q", items[0].FilePath, "/tmp/data.csv")
	}
	if items[0].ID == "" {
		t.Error("expected non-empty ID after enqueue")
	}
	if items[0].EnqueuedAt.IsZero() {
		t.Error("expected non-zero EnqueuedAt after enqueue")
	}
}

func TestAck(t *testing.T) {
	q := openQueue(t)

	q.Enqueue(&queue.Item{FilePath: "/tmp/done.csv"})
	items, _ := q.Dequeue(1)
	if err := q.Ack(items[0].ID); err != nil {
		t.Fatalf("Ack: %v", err)
	}
	if d := q.Depth(); d != 0 {
		t.Errorf("expected depth 0 after Ack, got %d", d)
	}
}

func TestNack_DeadLetter(t *testing.T) {
	q := openQueue(t)

	q.Enqueue(&queue.Item{FilePath: "/tmp/fail.csv"})
	items, _ := q.Dequeue(1)
	id := items[0].ID

	for i := 0; i < queue.MaxRetries; i++ {
		if err := q.Nack(id, "simulated error"); err != nil {
			t.Fatalf("Nack #%d: %v", i+1, err)
		}
	}

	if d := q.Depth(); d != 0 {
		t.Errorf("expected 0 pending after max retries, got %d", d)
	}
	if d := q.DeadLetterDepth(); d != 1 {
		t.Errorf("expected 1 dead-letter item, got %d", d)
	}
}

func TestNack_Increments(t *testing.T) {
	q := openQueue(t)

	q.Enqueue(&queue.Item{FilePath: "/tmp/retry.csv"})
	items, _ := q.Dequeue(1)
	id := items[0].ID

	if err := q.Nack(id, "temporary error"); err != nil {
		t.Fatalf("Nack: %v", err)
	}

	if d := q.Depth(); d != 1 {
		t.Errorf("expected 1 pending after 1 nack, got %d", d)
	}
	if d := q.DeadLetterDepth(); d != 0 {
		t.Errorf("expected 0 dead-letter after 1 nack, got %d", d)
	}

	items, _ = q.Dequeue(1)
	if items[0].RetryCount != 1 {
		t.Errorf("expected RetryCount 1, got %d", items[0].RetryCount)
	}
	if items[0].LastError != "temporary error" {
		t.Errorf("expected LastError %q, got %q", "temporary error", items[0].LastError)
	}
}

func TestFIFOOrder(t *testing.T) {
	q := openQueue(t)

	files := []string{"/tmp/a.csv", "/tmp/b.csv", "/tmp/c.csv"}
	for _, f := range files {
		if err := q.Enqueue(&queue.Item{FilePath: f}); err != nil {
			t.Fatalf("Enqueue %s: %v", f, err)
		}
	}
	if d := q.Depth(); d != 3 {
		t.Fatalf("expected depth 3, got %d", d)
	}

	items, err := q.Dequeue(3)
	if err != nil {
		t.Fatalf("Dequeue: %v", err)
	}
	if len(items) != 3 {
		t.Fatalf("expected 3 items, got %d", len(items))
	}

	// BBolt cursor iterates in key order; keys are zero-padded sequence IDs,
	// so order should be A, B, C.
	for i, f := range files {
		if items[i].FilePath != f {
			t.Errorf("item[%d]: got %q, want %q", i, items[i].FilePath, f)
		}
	}
}

func TestMaxQueueSizeConstant(t *testing.T) {
	// Verify the MaxQueueSize constant is set to the expected value.
	if queue.MaxQueueSize != 10000 {
		t.Errorf("MaxQueueSize: got %d, want 10000", queue.MaxQueueSize)
	}
}

func TestDequeueEmpty(t *testing.T) {
	q := openQueue(t)

	items, err := q.Dequeue(10)
	if err != nil {
		t.Fatalf("Dequeue on empty: %v", err)
	}
	if len(items) != 0 {
		t.Errorf("expected 0 items from empty queue, got %d", len(items))
	}
}

func TestStats(t *testing.T) {
	q := openQueue(t)

	pending, dl := q.Stats()
	if pending != 0 || dl != 0 {
		t.Errorf("initial stats: pending=%d, dl=%d, want 0,0", pending, dl)
	}

	for i := 0; i < 5; i++ {
		q.Enqueue(&queue.Item{FilePath: "/tmp/stats.csv"})
	}
	if d := q.Depth(); d != 5 {
		t.Errorf("pending after 5 enqueues: got %d, want 5", d)
	}
}

func TestNack_NonexistentItem(t *testing.T) {
	q := openQueue(t)

	err := q.Nack("nonexistent-id", "error")
	if err == nil {
		t.Error("expected error when nacking nonexistent item")
	}
}
