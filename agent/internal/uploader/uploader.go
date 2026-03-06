// Package uploader handles HTTPS multipart file uploads to the LabLink backend
// with exponential backoff retry.
package uploader

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log/slog"
	"mime/multipart"
	"net/http"
	"net/url"
	"os"
	"path/filepath"
	"time"
)

// backoffDurations defines the wait between upload retries: 1s, 5s, 25s.
var backoffDurations = []time.Duration{
	1 * time.Second,
	5 * time.Second,
	25 * time.Second,
}

// Uploader uploads files to the LabLink backend API.
type Uploader struct {
	baseURL    string
	agentID    string
	token      string
	httpClient *http.Client
}

// uploadResponse represents the parsed response from a successful upload.
type uploadResponse struct {
	Data struct {
		ID string `json:"id"`
	} `json:"data"`
}

// New creates an Uploader with the given configuration.
func New(baseURL, agentID, token, proxyURL string) *Uploader {
	transport := &http.Transport{
		Proxy: http.ProxyFromEnvironment,
	}
	if proxyURL != "" {
		proxyParsed, err := url.Parse(proxyURL)
		if err == nil {
			transport.Proxy = http.ProxyURL(proxyParsed)
		}
	}
	return &Uploader{
		baseURL: baseURL,
		agentID: agentID,
		token:   token,
		httpClient: &http.Client{
			Timeout:   60 * time.Second,
			Transport: transport,
		},
	}
}

// Upload sends a file to POST /api/v1/uploads as multipart form-data.
// It includes exponential backoff retry (1s, 5s, 25s) for up to 3 retries
// after the initial attempt. Returns nil on success.
func (u *Uploader) Upload(ctx context.Context, filePath string) error {
	var lastErr error

	for attempt := 0; attempt <= len(backoffDurations); attempt++ {
		if attempt > 0 {
			wait := backoffDurations[attempt-1]
			slog.Debug("uploader: retrying after backoff",
				"file", filePath,
				"attempt", attempt+1,
				"wait", wait,
			)
			select {
			case <-ctx.Done():
				return ctx.Err()
			case <-time.After(wait):
			}
		}

		lastErr = u.doUpload(ctx, filePath)
		if lastErr == nil {
			return nil
		}
		slog.Warn("uploader: upload attempt failed",
			"file", filePath,
			"attempt", attempt+1,
			"error", lastErr,
		)
		// Do not retry non-transient errors (e.g., file not found).
		if errors.Is(lastErr, os.ErrNotExist) {
			return lastErr
		}
	}

	return fmt.Errorf("upload failed after %d attempts: %w", len(backoffDurations)+1, lastErr)
}

func (u *Uploader) doUpload(ctx context.Context, filePath string) error {
	f, err := os.Open(filePath)
	if err != nil {
		// Wrap the original error to preserve os.ErrNotExist for retry logic.
		return fmt.Errorf("opening file: %w", err)
	}
	defer f.Close()

	var buf bytes.Buffer
	mw := multipart.NewWriter(&buf)

	part, err := mw.CreateFormFile("file", filepath.Base(filePath))
	if err != nil {
		return fmt.Errorf("creating form file: %w", err)
	}
	if _, err := io.Copy(part, f); err != nil {
		return fmt.Errorf("copying file data: %w", err)
	}

	// Include metadata fields.
	hostname, _ := os.Hostname()
	metadata := map[string]string{
		"agent_id":      u.agentID,
		"hostname":      hostname,
		"original_path": filePath,
	}
	for k, v := range metadata {
		if err := mw.WriteField(k, v); err != nil {
			return fmt.Errorf("writing field %s: %w", k, err)
		}
	}
	mw.Close()

	req, err := http.NewRequestWithContext(ctx, http.MethodPost,
		u.baseURL+"/uploads", &buf)
	if err != nil {
		return fmt.Errorf("creating request: %w", err)
	}
	req.Header.Set("Content-Type", mw.FormDataContentType())
	req.Header.Set("Authorization", "Bearer "+u.token)
	req.Header.Set("User-Agent", "lablink-agent")

	resp, err := u.httpClient.Do(req)
	if err != nil {
		return fmt.Errorf("http request: %w", err)
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return fmt.Errorf("reading response: %w", err)
	}

	if resp.StatusCode >= 400 {
		return fmt.Errorf("server returned %d: %s", resp.StatusCode, body)
	}

	var result uploadResponse
	if err := json.Unmarshal(body, &result); err != nil {
		slog.Debug("uploader: could not parse upload response", "error", err)
	} else if result.Data.ID != "" {
		slog.Info("uploader: upload successful", "upload_id", result.Data.ID, "file", filePath)
	}

	return nil
}
