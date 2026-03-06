// Package queue implements a persistent BBolt-backed upload queue with retry
// counters and a dead-letter bucket for permanently-failed items.
package queue

import (
	"encoding/json"
	"fmt"
	"time"

	bolt "go.etcd.io/bbolt"
)

const (
	bucketPending    = "pending"
	bucketDeadLetter = "dead_letter"

	// MaxRetries is the number of upload attempts before an item is
	// moved to the dead-letter bucket.
	MaxRetries = 3

	// MaxQueueSize is the maximum number of entries allowed in the
	// pending bucket.
	MaxQueueSize = 10000
)

// Item represents a queued upload job.
type Item struct {
	ID         string    `json:"id"`
	FilePath   string    `json:"file_path"`
	EnqueuedAt time.Time `json:"enqueued_at"`
	RetryCount int       `json:"retry_count"`
	LastError  string    `json:"last_error,omitempty"`
}

// Queue wraps a BBolt database providing enqueue, dequeue, ack and nack
// operations for upload jobs.
type Queue struct {
	db *bolt.DB
}

// Open opens (or creates) the BBolt database at path.
func Open(path string) (*Queue, error) {
	db, err := bolt.Open(path, 0o600, &bolt.Options{Timeout: 2 * time.Second})
	if err != nil {
		return nil, fmt.Errorf("opening bolt db: %w", err)
	}
	if err := db.Update(func(tx *bolt.Tx) error {
		if _, err := tx.CreateBucketIfNotExists([]byte(bucketPending)); err != nil {
			return err
		}
		_, err := tx.CreateBucketIfNotExists([]byte(bucketDeadLetter))
		return err
	}); err != nil {
		db.Close()
		return nil, fmt.Errorf("creating buckets: %w", err)
	}
	return &Queue{db: db}, nil
}

// Close releases the underlying database handle.
func (q *Queue) Close() error { return q.db.Close() }

// Enqueue adds a new item to the pending bucket. Returns an error if the
// queue has reached MaxQueueSize.
func (q *Queue) Enqueue(item *Item) error {
	return q.db.Update(func(tx *bolt.Tx) error {
		b := tx.Bucket([]byte(bucketPending))

		// Enforce max queue size.
		if b.Stats().KeyN >= MaxQueueSize {
			return fmt.Errorf("queue is full (%d items)", MaxQueueSize)
		}

		id, _ := b.NextSequence()
		item.ID = fmt.Sprintf("%020d", id)
		item.EnqueuedAt = time.Now()
		data, err := json.Marshal(item)
		if err != nil {
			return err
		}
		return b.Put([]byte(item.ID), data)
	})
}

// Dequeue returns up to n items from the front of the pending bucket without
// removing them. Call Ack to remove or Nack to increment the retry counter.
func (q *Queue) Dequeue(n int) ([]*Item, error) {
	var items []*Item
	err := q.db.View(func(tx *bolt.Tx) error {
		b := tx.Bucket([]byte(bucketPending))
		c := b.Cursor()
		for k, v := c.First(); k != nil && len(items) < n; k, v = c.Next() {
			var item Item
			if err := json.Unmarshal(v, &item); err != nil {
				continue
			}
			items = append(items, &item)
		}
		return nil
	})
	return items, err
}

// Ack removes an item from the pending bucket (upload succeeded).
func (q *Queue) Ack(id string) error {
	return q.db.Update(func(tx *bolt.Tx) error {
		return tx.Bucket([]byte(bucketPending)).Delete([]byte(id))
	})
}

// Nack increments the retry counter. If the item has exceeded MaxRetries it
// is moved to the dead-letter bucket.
func (q *Queue) Nack(id string, errMsg string) error {
	return q.db.Update(func(tx *bolt.Tx) error {
		b := tx.Bucket([]byte(bucketPending))
		data := b.Get([]byte(id))
		if data == nil {
			return fmt.Errorf("item %s not found", id)
		}
		var item Item
		if err := json.Unmarshal(data, &item); err != nil {
			return err
		}
		item.RetryCount++
		item.LastError = errMsg

		if item.RetryCount >= MaxRetries {
			dl := tx.Bucket([]byte(bucketDeadLetter))
			updated, _ := json.Marshal(item)
			if err := dl.Put([]byte(id), updated); err != nil {
				return err
			}
			return b.Delete([]byte(id))
		}

		updated, _ := json.Marshal(item)
		return b.Put([]byte(id), updated)
	})
}

// Depth returns the number of items in the pending bucket.
func (q *Queue) Depth() int {
	var n int
	q.db.View(func(tx *bolt.Tx) error { //nolint:errcheck
		n = tx.Bucket([]byte(bucketPending)).Stats().KeyN
		return nil
	})
	return n
}

// DeadLetterDepth returns the number of items in the dead-letter bucket.
func (q *Queue) DeadLetterDepth() int {
	var n int
	q.db.View(func(tx *bolt.Tx) error { //nolint:errcheck
		n = tx.Bucket([]byte(bucketDeadLetter)).Stats().KeyN
		return nil
	})
	return n
}

// Stats returns pending and dead-letter counts.
func (q *Queue) Stats() (pending int, deadLetter int) {
	return q.Depth(), q.DeadLetterDepth()
}
