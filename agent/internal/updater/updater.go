// Package updater checks GitHub Releases for a newer version of the agent,
// downloads it, verifies the SHA-256 checksum, and replaces the running binary.
package updater

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"os"
	"runtime"
	"strings"
	"time"

	"golang.org/x/mod/semver"
)

const (
	githubReleasesURL = "https://api.github.com/repos/william-c-stanford/lablink/releases/latest"
	checkInterval     = 24 * time.Hour
)

// Release is a partial representation of the GitHub Releases API response.
type Release struct {
	TagName string  `json:"tag_name"`
	Assets  []Asset `json:"assets"`
}

// Asset is a single downloadable file attached to a release.
type Asset struct {
	Name               string `json:"name"`
	BrowserDownloadURL string `json:"browser_download_url"`
}

// Updater periodically checks for and applies agent updates.
type Updater struct {
	currentVersion string
}

// New creates an Updater.
func New(currentVersion string) *Updater {
	return &Updater{currentVersion: currentVersion}
}

// Run checks for updates immediately then every 24 hours.
func (u *Updater) Run(ctx context.Context) {
	u.check(ctx)
	ticker := time.NewTicker(checkInterval)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			u.check(ctx)
		}
	}
}

func (u *Updater) check(ctx context.Context) {
	release, err := u.latestRelease(ctx)
	if err != nil {
		slog.Debug("updater: cannot check for updates", "error", err)
		return
	}

	// Normalise tags: "0.2.0" -> "v0.2.0"
	latest := release.TagName
	if !strings.HasPrefix(latest, "v") {
		latest = "v" + latest
	}
	current := u.currentVersion
	if !strings.HasPrefix(current, "v") {
		current = "v" + current
	}

	if semver.Compare(latest, current) <= 0 {
		slog.Debug("updater: already up to date", "version", current)
		return
	}

	slog.Info("updater: new version available", "latest", latest, "current", current)
	if err := u.applyUpdate(ctx, release); err != nil {
		slog.Error("updater: update failed", "error", err)
	}
}

func (u *Updater) latestRelease(ctx context.Context) (*Release, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, githubReleasesURL, nil)
	if err != nil {
		return nil, err
	}
	req.Header.Set("Accept", "application/vnd.github+json")

	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	var release Release
	if err := json.NewDecoder(resp.Body).Decode(&release); err != nil {
		return nil, err
	}
	return &release, nil
}

func (u *Updater) applyUpdate(ctx context.Context, release *Release) error {
	binaryName := fmt.Sprintf("lablink-agent-%s-%s", runtime.GOOS, runtime.GOARCH)
	checksumName := binaryName + ".sha256"

	var binaryURL, checksumURL string
	for _, a := range release.Assets {
		switch a.Name {
		case binaryName:
			binaryURL = a.BrowserDownloadURL
		case checksumName:
			checksumURL = a.BrowserDownloadURL
		}
	}
	if binaryURL == "" {
		return fmt.Errorf("no binary asset for %s/%s in release %s", runtime.GOOS, runtime.GOARCH, release.TagName)
	}

	// Download checksum file first.
	expectedHash, err := u.downloadText(ctx, checksumURL)
	if err != nil {
		return fmt.Errorf("downloading checksum: %w", err)
	}
	expectedHash = strings.TrimSpace(strings.Fields(expectedHash)[0])

	// Download binary to a temp file.
	tmp, err := os.CreateTemp("", "lablink-agent-update-*")
	if err != nil {
		return err
	}
	defer os.Remove(tmp.Name())

	h := sha256.New()
	if err := u.downloadTo(ctx, binaryURL, io.MultiWriter(tmp, h)); err != nil {
		tmp.Close()
		return fmt.Errorf("downloading binary: %w", err)
	}
	tmp.Close()

	actualHash := hex.EncodeToString(h.Sum(nil))
	if actualHash != expectedHash {
		return fmt.Errorf("checksum mismatch: got %s, want %s", actualHash, expectedHash)
	}

	// Replace running binary.
	exePath, err := os.Executable()
	if err != nil {
		return err
	}
	if err := os.Chmod(tmp.Name(), 0o755); err != nil {
		return err
	}
	if err := os.Rename(tmp.Name(), exePath); err != nil {
		return fmt.Errorf("replacing binary: %w", err)
	}

	slog.Info("updater: update applied -- restarting", "version", release.TagName)
	// Signal the OS to exec the new binary (graceful restart).
	// For simplicity we exit and rely on a process supervisor to restart.
	os.Exit(0)
	return nil
}

func (u *Updater) downloadText(ctx context.Context, url string) (string, error) {
	if url == "" {
		return "", fmt.Errorf("empty URL")
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return "", err
	}
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()
	b, err := io.ReadAll(resp.Body)
	return string(b), err
}

func (u *Updater) downloadTo(ctx context.Context, url string, w io.Writer) error {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return err
	}
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	_, err = io.Copy(w, resp.Body)
	return err
}
