// Package watcher monitors directories for new instrument output files and
// sends stable file paths to a channel for queueing.
package watcher

import (
	"log/slog"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"time"

	"github.com/fsnotify/fsnotify"
	"github.com/william-c-stanford/lablink/agent/internal/config"
)

const (
	// stabilityInterval is how long a file's size must remain unchanged
	// before it is considered stable and ready for upload.
	stabilityInterval = 1 * time.Second
	// stabilityChecks is the number of consecutive stable checks required.
	stabilityChecks = 5
)

// Watcher watches one or more directories for new files and sends stable
// file paths to the output channel.
type Watcher struct {
	fsw     *fsnotify.Watcher
	folders []config.WatchedFolder
	outCh   chan<- string
	mu      sync.Mutex
	pending map[string]*pendingFile
	done    chan struct{}
}

type pendingFile struct {
	lastSize    int64
	stableCount int
	timer       *time.Timer
	folder      config.WatchedFolder
}

// New creates a Watcher for the given folders. Stable file paths are sent to outCh.
func New(folders []config.WatchedFolder, outCh chan<- string) (*Watcher, error) {
	fsw, err := fsnotify.NewWatcher()
	if err != nil {
		return nil, err
	}
	return &Watcher{
		fsw:     fsw,
		folders: folders,
		outCh:   outCh,
		pending: make(map[string]*pendingFile),
		done:    make(chan struct{}),
	}, nil
}

// Start begins watching all configured directories.
func (w *Watcher) Start() error {
	for _, f := range w.folders {
		if err := w.fsw.Add(f.Path); err != nil {
			slog.Warn("watcher: cannot watch directory", "path", f.Path, "error", err)
			continue
		}
		slog.Info("watcher: watching directory", "path", f.Path)
	}
	go w.loop()
	return nil
}

// Stop shuts down the watcher.
func (w *Watcher) Stop() {
	close(w.done)
	w.fsw.Close()
}

func (w *Watcher) loop() {
	for {
		select {
		case <-w.done:
			return
		case event, ok := <-w.fsw.Events:
			if !ok {
				return
			}
			if event.Has(fsnotify.Create) || event.Has(fsnotify.Write) {
				w.handleEvent(event.Name)
			}
		case err, ok := <-w.fsw.Errors:
			if !ok {
				return
			}
			slog.Error("watcher: fsnotify error", "error", err)
		}
	}
}

func (w *Watcher) handleEvent(path string) {
	// Ignore hidden files (starting with .)
	base := filepath.Base(path)
	if strings.HasPrefix(base, ".") {
		slog.Debug("watcher: ignoring hidden file", "file", path)
		return
	}

	// Ignore temporary files (~, .tmp, .swp)
	if isTemporaryFile(base) {
		slog.Debug("watcher: ignoring temporary file", "file", path)
		return
	}

	folder, ok := w.folderFor(path)
	if !ok {
		return
	}
	if !w.isAllowed(path, folder) {
		return
	}

	w.mu.Lock()
	defer w.mu.Unlock()

	if pf, exists := w.pending[path]; exists {
		// Reset the stability counter on further writes.
		pf.stableCount = 0
		pf.timer.Reset(stabilityInterval)
		return
	}

	pf := &pendingFile{
		folder: folder,
	}
	pf.timer = time.AfterFunc(stabilityInterval, func() {
		w.checkStability(path)
	})
	w.pending[path] = pf

	slog.Debug("watcher: new file detected, starting stability check", "file", path)
}

func (w *Watcher) checkStability(path string) {
	w.mu.Lock()
	pf, ok := w.pending[path]
	if !ok {
		w.mu.Unlock()
		return
	}

	info, err := os.Stat(path)
	if err != nil {
		// File was removed before it stabilized.
		delete(w.pending, path)
		w.mu.Unlock()
		return
	}

	currentSize := info.Size()
	if currentSize != pf.lastSize {
		// Size changed -- reset stability counter.
		pf.lastSize = currentSize
		pf.stableCount = 0
		pf.timer.Reset(stabilityInterval)
		w.mu.Unlock()
		return
	}

	// Size unchanged for this check.
	pf.stableCount++
	if pf.stableCount < stabilityChecks {
		pf.timer.Reset(stabilityInterval)
		w.mu.Unlock()
		return
	}

	// File is stable (size unchanged for 5 consecutive 1-second checks).
	delete(w.pending, path)
	w.mu.Unlock()

	slog.Info("watcher: file stable, sending to queue", "file", path)
	w.outCh <- path
}

// folderFor returns the WatchedFolder whose path is a prefix of filePath.
func (w *Watcher) folderFor(filePath string) (config.WatchedFolder, bool) {
	for _, f := range w.folders {
		if strings.HasPrefix(filePath, f.Path) {
			return f, true
		}
	}
	return config.WatchedFolder{}, false
}

// isAllowed checks whether the file extension passes the folder's filter (or
// the global default whitelist).
func (w *Watcher) isAllowed(path string, folder config.WatchedFolder) bool {
	ext := strings.ToLower(filepath.Ext(path))
	if ext == "" {
		return false
	}
	allowed := folder.Extensions
	if len(allowed) == 0 {
		allowed = config.DefaultExtensions
	}
	for _, a := range allowed {
		if a == ext {
			return true
		}
	}
	return false
}

// isTemporaryFile returns true for common temporary file patterns.
func isTemporaryFile(name string) bool {
	if strings.HasSuffix(name, "~") {
		return true
	}
	if strings.HasSuffix(name, ".tmp") {
		return true
	}
	if strings.HasSuffix(name, ".swp") {
		return true
	}
	return false
}
