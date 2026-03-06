package cmd

import (
	"bytes"
	"context"
	"crypto/rand"
	"encoding/json"
	"fmt"
	"io"
	"log/slog"
	"math/big"
	"net/http"
	"net/url"
	"os"
	"runtime"
	"time"

	"github.com/spf13/cobra"
	"github.com/william-c-stanford/lablink/agent/internal/config"
)

var registerCmd = &cobra.Command{
	Use:   "register",
	Short: "Register this agent with the LabLink platform",
	Long: `Register initiates the 6-digit pairing flow.

The agent generates a random 6-digit code and sends it to the LabLink backend
along with hostname and platform info. The code is displayed in the terminal.
Open the LabLink dashboard, go to Settings -> Agents, and enter the code to
approve this machine.

Once approved the agent token is saved to ~/.lablink/agent.yaml and the agent
is ready to start.`,
	RunE: runRegister,
}

var apiURLFlag string

func init() {
	registerCmd.Flags().StringVar(&apiURLFlag, "api-url", "",
		"LabLink backend URL (e.g. https://app.lablink.io/api/v1) -- overrides config")
}

// registerResponse represents the backend's response to pair-status polling.
type registerResponse struct {
	Data struct {
		AgentID    string `json:"agent_id"`
		AgentToken string `json:"agent_token"`
		Status     string `json:"status"`
	} `json:"data"`
}

func runRegister(cmd *cobra.Command, args []string) error {
	// Allow --api-url to bootstrap registration even before config exists.
	if apiURLFlag != "" {
		cfg.APIURL = apiURLFlag
	}
	if cfg.APIURL == "" {
		return fmt.Errorf("api_url not set -- provide --api-url or set it in ~/.lablink/agent.yaml")
	}

	hostname, err := os.Hostname()
	if err != nil {
		hostname = "unknown"
	}

	// Generate a random 6-digit pairing code.
	code, err := generatePairingCode()
	if err != nil {
		return fmt.Errorf("generating pairing code: %w", err)
	}

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Minute)
	defer cancel()

	fmt.Println()
	fmt.Println("  LabLink Agent Registration")
	fmt.Println("  --------------------------")
	fmt.Printf("  Connecting to %s ...\n", cfg.APIURL)

	// POST /api/v1/agents/register with pairing info.
	regBody := map[string]string{
		"pairing_code": code,
		"hostname":     hostname,
		"os":           runtime.GOOS,
		"arch":         runtime.GOARCH,
	}
	bodyBytes, _ := json.Marshal(regBody)

	req, err := http.NewRequestWithContext(ctx, http.MethodPost,
		cfg.APIURL+"/agents/register", bytes.NewReader(bodyBytes))
	if err != nil {
		return fmt.Errorf("creating register request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")

	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return fmt.Errorf("sending register request: %w", err)
	}
	resp.Body.Close()

	if resp.StatusCode >= 400 {
		return fmt.Errorf("registration request failed with status %d", resp.StatusCode)
	}

	fmt.Println()
	fmt.Printf("  Enter this code in your LabLink dashboard: %s\n", formatCode(code))
	fmt.Println()
	fmt.Println("  Open the LabLink dashboard -> Settings -> Agents")
	fmt.Println("  and enter the code above to approve this machine.")
	fmt.Println()
	fmt.Println("  Waiting for approval (timeout: 5 minutes) ...")

	// Poll GET /api/v1/agents/pair-status?code=XXXXXX every 3 seconds.
	ticker := time.NewTicker(3 * time.Second)
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			return fmt.Errorf("registration timed out -- please try again")
		case <-ticker.C:
			pairURL := fmt.Sprintf("%s/agents/pair-status?code=%s",
				cfg.APIURL, url.QueryEscape(code))
			pollReq, err := http.NewRequestWithContext(ctx, http.MethodGet, pairURL, nil)
			if err != nil {
				continue
			}
			pollResp, err := http.DefaultClient.Do(pollReq)
			if err != nil {
				slog.Debug("poll pairing: waiting for approval", "error", err)
				continue
			}
			pollBody, _ := io.ReadAll(pollResp.Body)
			pollResp.Body.Close()

			if pollResp.StatusCode >= 400 {
				slog.Debug("poll pairing: not yet approved", "status", pollResp.StatusCode)
				continue
			}

			var result registerResponse
			if err := json.Unmarshal(pollBody, &result); err != nil {
				slog.Debug("poll pairing: parse error", "error", err)
				continue
			}

			if result.Data.AgentToken != "" {
				// Persist the credentials.
				cfg.AgentID = result.Data.AgentID
				cfg.AgentToken = result.Data.AgentToken

				path, _ := config.ConfigPath(cfgPath)
				if err := config.Save(cfg, path); err != nil {
					return fmt.Errorf("saving config: %w", err)
				}

				fmt.Println()
				fmt.Printf("  Registered! Agent ID: %s\n", result.Data.AgentID)
				fmt.Printf("  Config saved to: %s\n", path)
				fmt.Println()
				fmt.Println("  Run 'lablink-agent start' to begin watching directories.")
				fmt.Println()

				slog.Info("registration complete", "agent_id", result.Data.AgentID)
				return nil
			}
		}
	}
}

// generatePairingCode returns a cryptographically random 6-digit string.
func generatePairingCode() (string, error) {
	max := big.NewInt(1000000)
	n, err := rand.Int(rand.Reader, max)
	if err != nil {
		return "", err
	}
	return fmt.Sprintf("%06d", n.Int64()), nil
}

// formatCode inserts a dash in the middle for readability: "123456" -> "123-456"
func formatCode(code string) string {
	if len(code) == 6 {
		return code[:3] + "-" + code[3:]
	}
	return code
}
