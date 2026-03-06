package uploader_test

import (
	"context"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"sync/atomic"
	"testing"

	"github.com/william-c-stanford/lablink/agent/internal/uploader"
)

func TestUploadSuccess(t *testing.T) {
	var received atomic.Bool
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/uploads" {
			t.Errorf("unexpected path: %s", r.URL.Path)
		}
		if r.Method != http.MethodPost {
			t.Errorf("unexpected method: %s", r.Method)
		}
		auth := r.Header.Get("Authorization")
		if auth != "Bearer test-token" {
			t.Errorf("Authorization: got %q, want %q", auth, "Bearer test-token")
		}

		if err := r.ParseMultipartForm(10 << 20); err != nil {
			t.Errorf("ParseMultipartForm: %v", err)
		}
		_, header, err := r.FormFile("file")
		if err != nil {
			t.Errorf("FormFile: %v", err)
			w.WriteHeader(http.StatusBadRequest)
			return
		}
		if header.Filename != "upload.csv" {
			t.Errorf("filename: got %q, want %q", header.Filename, "upload.csv")
		}

		received.Store(true)
		w.WriteHeader(http.StatusOK)
		w.Write([]byte(`{"data":{"id":"upload-123"}}`))
	}))
	t.Cleanup(srv.Close)

	ul := uploader.New(srv.URL, "test-agent", "test-token", "")

	dir := t.TempDir()
	filePath := filepath.Join(dir, "upload.csv")
	os.WriteFile(filePath, []byte("col1,col2\n1,2\n"), 0o644)

	err := ul.Upload(context.Background(), filePath)
	if err != nil {
		t.Fatalf("Upload: %v", err)
	}
	if !received.Load() {
		t.Error("server never received the upload")
	}
}

func TestUploadRetry(t *testing.T) {
	var attempts atomic.Int32
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		n := attempts.Add(1)
		if n <= 2 {
			w.WriteHeader(http.StatusInternalServerError)
			w.Write([]byte(`{"errors":[{"code":"SERVER_ERROR","message":"temporary"}]}`))
			return
		}
		w.WriteHeader(http.StatusOK)
		w.Write([]byte(`{"data":{"id":"upload-456"}}`))
	}))
	t.Cleanup(srv.Close)

	ul := uploader.New(srv.URL, "test-agent", "test-token", "")

	dir := t.TempDir()
	filePath := filepath.Join(dir, "retry.csv")
	os.WriteFile(filePath, []byte("data"), 0o644)

	err := ul.Upload(context.Background(), filePath)
	if err != nil {
		t.Fatalf("Upload should have succeeded after retries: %v", err)
	}
	if n := attempts.Load(); n != 3 {
		t.Errorf("expected 3 attempts (2 failures + 1 success), got %d", n)
	}
}

func TestUploadMaxRetries(t *testing.T) {
	var attempts atomic.Int32
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		attempts.Add(1)
		w.WriteHeader(http.StatusInternalServerError)
		w.Write([]byte(`{"errors":[{"code":"SERVER_ERROR","message":"permanent"}]}`))
	}))
	t.Cleanup(srv.Close)

	ul := uploader.New(srv.URL, "test-agent", "test-token", "")

	dir := t.TempDir()
	filePath := filepath.Join(dir, "fail.csv")
	os.WriteFile(filePath, []byte("data"), 0o644)

	err := ul.Upload(context.Background(), filePath)
	if err == nil {
		t.Fatal("expected error after max retries, got nil")
	}
	// Should have attempted 4 times total (initial + 3 retries).
	if n := attempts.Load(); n != 4 {
		t.Errorf("expected 4 total attempts, got %d", n)
	}
}

func TestUploadMissingFile(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))
	t.Cleanup(srv.Close)

	ul := uploader.New(srv.URL, "test-agent", "test-token", "")
	err := ul.Upload(context.Background(), "/nonexistent/file.csv")
	if err == nil {
		t.Fatal("expected error when uploading nonexistent file")
	}
}
