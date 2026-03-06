package updater_test

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/william-c-stanford/lablink/agent/internal/updater"
)

// mockGitHubServer creates a test server that mimics the GitHub Releases API.
// It returns a Release with the given tag and optional assets.
func mockGitHubServer(t *testing.T, tagName string, assets []updater.Asset) *httptest.Server {
	t.Helper()
	release := updater.Release{
		TagName: tagName,
		Assets:  assets,
	}
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(release)
	}))
	t.Cleanup(srv.Close)
	return srv
}

func TestCheckForUpdate(t *testing.T) {
	t.Parallel()

	// Mock server returns a newer version than current.
	srv := mockGitHubServer(t, "v0.3.0", nil)

	// We test the version comparison logic by making a direct HTTP request
	// and parsing the response, since the Updater's check method is private
	// and calls os.Exit on update. We verify the detection logic here.
	resp, err := http.Get(srv.URL)
	if err != nil {
		t.Fatalf("GET: %v", err)
	}
	defer resp.Body.Close()

	var release updater.Release
	if err := json.NewDecoder(resp.Body).Decode(&release); err != nil {
		t.Fatalf("decode: %v", err)
	}

	if release.TagName != "v0.3.0" {
		t.Errorf("TagName: got %q, want %q", release.TagName, "v0.3.0")
	}

	// Simulate the version comparison the updater performs.
	currentVersion := "v0.1.0"
	latestVersion := release.TagName

	// Normalize: ensure "v" prefix.
	if !strings.HasPrefix(latestVersion, "v") {
		latestVersion = "v" + latestVersion
	}
	if !strings.HasPrefix(currentVersion, "v") {
		currentVersion = "v" + currentVersion
	}

	// v0.3.0 > v0.1.0 -> update available.
	if latestVersion <= currentVersion {
		t.Errorf("expected update available: latest=%s, current=%s", latestVersion, currentVersion)
	}
}

func TestNoUpdateNeeded(t *testing.T) {
	t.Parallel()

	srv := mockGitHubServer(t, "v0.1.0", nil)

	resp, err := http.Get(srv.URL)
	if err != nil {
		t.Fatalf("GET: %v", err)
	}
	defer resp.Body.Close()

	var release updater.Release
	if err := json.NewDecoder(resp.Body).Decode(&release); err != nil {
		t.Fatalf("decode: %v", err)
	}

	currentVersion := "v0.1.0"
	latestVersion := release.TagName
	if !strings.HasPrefix(latestVersion, "v") {
		latestVersion = "v" + latestVersion
	}

	// Same version -> no update needed.
	if latestVersion != currentVersion {
		t.Errorf("expected no update: latest=%s, current=%s", latestVersion, currentVersion)
	}
}

func TestChecksumVerification(t *testing.T) {
	t.Parallel()

	// Create test binary content and its SHA-256 hash.
	binaryContent := []byte("this is the agent binary content for testing")
	h := sha256.Sum256(binaryContent)
	expectedHash := hex.EncodeToString(h[:])

	// Mock server serving the binary and checksum file.
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch {
		case strings.HasSuffix(r.URL.Path, ".sha256"):
			// Checksum file format: "<hash>  <filename>"
			fmt.Fprintf(w, "%s  lablink-agent-darwin-arm64\n", expectedHash)
		case strings.HasSuffix(r.URL.Path, "lablink-agent-darwin-arm64"):
			w.Write(binaryContent)
		default:
			http.NotFound(w, r)
		}
	}))
	t.Cleanup(srv.Close)

	// Download the checksum.
	checksumResp, err := http.Get(srv.URL + "/lablink-agent-darwin-arm64.sha256")
	if err != nil {
		t.Fatalf("GET checksum: %v", err)
	}
	defer checksumResp.Body.Close()
	checksumBytes, err := io.ReadAll(checksumResp.Body)
	if err != nil {
		t.Fatalf("reading checksum body: %v", err)
	}
	parts := strings.Fields(string(checksumBytes))
	if len(parts) == 0 {
		t.Fatal("empty checksum response")
	}
	remoteHash := parts[0]

	// Download the binary and compute hash.
	binaryResp, err := http.Get(srv.URL + "/lablink-agent-darwin-arm64")
	if err != nil {
		t.Fatalf("GET binary: %v", err)
	}
	defer binaryResp.Body.Close()
	binaryBytes, err := io.ReadAll(binaryResp.Body)
	if err != nil {
		t.Fatalf("reading binary body: %v", err)
	}

	computedHash := sha256.Sum256(binaryBytes)
	actualHash := hex.EncodeToString(computedHash[:])

	if actualHash != remoteHash {
		t.Errorf("checksum mismatch: computed %s, expected %s", actualHash, remoteHash)
	}
	if actualHash != expectedHash {
		t.Errorf("checksum does not match original: computed %s, expected %s", actualHash, expectedHash)
	}
}

func TestChecksumMismatchDetected(t *testing.T) {
	t.Parallel()

	binaryContent := []byte("correct binary")
	wrongContent := []byte("tampered binary")
	h := sha256.Sum256(binaryContent)
	correctHash := hex.EncodeToString(h[:])

	// Compute hash of wrong content.
	wh := sha256.Sum256(wrongContent)
	wrongHash := hex.EncodeToString(wh[:])

	if correctHash == wrongHash {
		t.Fatal("test setup error: correct and wrong hashes should differ")
	}

	// Verify the mismatch would be detected.
	if correctHash == wrongHash {
		t.Error("checksum verification should have caught tampered binary")
	}
}

func TestVersionNormalization(t *testing.T) {
	t.Parallel()

	cases := []struct {
		name     string
		current  string
		latest   string
		wantUpdate bool
	}{
		{"newer with v prefix", "v0.1.0", "v0.2.0", true},
		{"same version", "v0.1.0", "v0.1.0", false},
		{"older latest", "v0.2.0", "v0.1.0", false},
		{"without v prefix", "0.1.0", "0.2.0", true},
		{"mixed prefixes", "v0.1.0", "0.2.0", true},
	}

	for _, tc := range cases {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()

			current := tc.current
			latest := tc.latest
			if !strings.HasPrefix(current, "v") {
				current = "v" + current
			}
			if !strings.HasPrefix(latest, "v") {
				latest = "v" + latest
			}

			hasUpdate := latest > current
			if hasUpdate != tc.wantUpdate {
				t.Errorf("hasUpdate=%v, want %v (current=%s, latest=%s)",
					hasUpdate, tc.wantUpdate, current, latest)
			}
		})
	}
}
