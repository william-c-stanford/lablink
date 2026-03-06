package watcher

import (
	"os"
	"path/filepath"
	"testing"
	"time"

	"github.com/william-c-stanford/lablink/agent/internal/config"
)

func TestIsTemporaryFile(t *testing.T) {
	tests := []struct {
		name string
		want bool
	}{
		{"data.csv", false},
		{"results.xml", false},
		{"data.csv~", true},
		{"tempfile.tmp", true},
		{".file.swp", true},
		{"normal.txt", false},
	}
	for _, tt := range tests {
		if got := isTemporaryFile(tt.name); got != tt.want {
			t.Errorf("isTemporaryFile(%q) = %v, want %v", tt.name, got, tt.want)
		}
	}
}

func TestIsAllowed(t *testing.T) {
	w := &Watcher{
		folders: []config.WatchedFolder{
			{Path: "/data", Extensions: []string{".csv", ".xml"}},
		},
	}

	folder := w.folders[0]

	tests := []struct {
		path string
		want bool
	}{
		{"/data/results.csv", true},
		{"/data/results.xml", true},
		{"/data/results.json", false},
		{"/data/results.txt", false},
		{"/data/noextension", false},
	}
	for _, tt := range tests {
		if got := w.isAllowed(tt.path, folder); got != tt.want {
			t.Errorf("isAllowed(%q) = %v, want %v", tt.path, got, tt.want)
		}
	}
}

func TestIsAllowed_DefaultExtensions(t *testing.T) {
	w := &Watcher{
		folders: []config.WatchedFolder{
			{Path: "/data"}, // no extensions = use defaults
		},
	}
	folder := w.folders[0]

	for _, ext := range config.DefaultExtensions {
		path := "/data/file" + ext
		if !w.isAllowed(path, folder) {
			t.Errorf("expected default extension %q to be allowed", ext)
		}
	}

	if w.isAllowed("/data/file.exe", folder) {
		t.Error("expected .exe to be rejected with default extensions")
	}
}

func TestFolderFor(t *testing.T) {
	w := &Watcher{
		folders: []config.WatchedFolder{
			{Path: "/data/instruments"},
			{Path: "/data/hplc"},
		},
	}

	if _, ok := w.folderFor("/data/instruments/output.csv"); !ok {
		t.Error("expected to find folder for /data/instruments/output.csv")
	}
	if _, ok := w.folderFor("/data/hplc/run1.cdf"); !ok {
		t.Error("expected to find folder for /data/hplc/run1.cdf")
	}
	if _, ok := w.folderFor("/other/path/file.csv"); ok {
		t.Error("expected no folder match for /other/path/file.csv")
	}
}

func TestWatcher_StabilityCheck(t *testing.T) {
	dir := t.TempDir()

	outCh := make(chan string, 10)
	folders := []config.WatchedFolder{
		{Path: dir, Extensions: []string{".csv"}},
	}

	w, err := New(folders, outCh)
	if err != nil {
		t.Fatalf("New: %v", err)
	}

	if err := w.Start(); err != nil {
		t.Fatalf("Start: %v", err)
	}
	defer w.Stop()

	// Create a file -- the watcher should detect it and send it through the
	// channel after 5 consecutive 1-second stability checks.
	testFile := filepath.Join(dir, "test_output.csv")
	if err := os.WriteFile(testFile, []byte("col1,col2\n1,2\n"), 0o644); err != nil {
		t.Fatalf("writing test file: %v", err)
	}

	select {
	case path := <-outCh:
		if path != testFile {
			t.Errorf("got path %q, want %q", path, testFile)
		}
	case <-time.After(15 * time.Second):
		t.Fatal("timed out waiting for stable file")
	}
}

func TestWatcher_IgnoresHiddenFiles(t *testing.T) {
	dir := t.TempDir()

	outCh := make(chan string, 10)
	folders := []config.WatchedFolder{
		{Path: dir, Extensions: []string{".csv"}},
	}

	w, err := New(folders, outCh)
	if err != nil {
		t.Fatalf("New: %v", err)
	}

	if err := w.Start(); err != nil {
		t.Fatalf("Start: %v", err)
	}
	defer w.Stop()

	// Create a hidden file -- should be ignored.
	hiddenFile := filepath.Join(dir, ".hidden.csv")
	if err := os.WriteFile(hiddenFile, []byte("data"), 0o644); err != nil {
		t.Fatalf("writing hidden file: %v", err)
	}

	// Also create a normal file so we know the watcher is working.
	normalFile := filepath.Join(dir, "normal.csv")
	if err := os.WriteFile(normalFile, []byte("data"), 0o644); err != nil {
		t.Fatalf("writing normal file: %v", err)
	}

	// We should receive the normal file but not the hidden one.
	select {
	case path := <-outCh:
		if path == hiddenFile {
			t.Error("watcher should not send hidden files")
		}
		if path != normalFile {
			t.Errorf("got unexpected path %q", path)
		}
	case <-time.After(15 * time.Second):
		t.Fatal("timed out waiting for file")
	}
}
