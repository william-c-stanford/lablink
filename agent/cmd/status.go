package cmd

import (
	"fmt"
	"os"
	"path/filepath"
	"text/tabwriter"

	"github.com/spf13/cobra"
	"github.com/william-c-stanford/lablink/agent/internal/config"
	"github.com/william-c-stanford/lablink/agent/internal/queue"
)

var statusCmd = &cobra.Command{
	Use:   "status",
	Short: "Show the agent's current status",
	Long: `Status prints a summary of the agent's registration state, queue depth,
and connectivity to the LabLink backend.`,
	RunE: runStatus,
}

func runStatus(cmd *cobra.Command, args []string) error {
	w := tabwriter.NewWriter(os.Stdout, 0, 0, 2, ' ', 0)
	defer w.Flush()

	fmt.Fprintln(w)
	fmt.Fprintln(w, "  LabLink Agent Status")
	fmt.Fprintln(w, "  --------------------")

	// Registration state.
	if !cfg.IsRegistered() {
		fmt.Fprintln(w, "  Registration:\tnot registered")
		fmt.Fprintln(w, "")
		fmt.Fprintln(w, "  Run 'lablink-agent register' to connect this machine.")
		fmt.Fprintln(w)
		return nil
	}
	fmt.Fprintf(w, "  Registration:\tregistered\n")
	fmt.Fprintf(w, "  Agent ID:\t%s\n", cfg.AgentID)
	fmt.Fprintf(w, "  API URL:\t%s\n", cfg.APIURL)

	// Watched folders.
	fmt.Fprintf(w, "  Watched dirs:\t%d\n", len(cfg.WatchedFolders))
	for _, f := range cfg.WatchedFolders {
		exts := "default"
		if len(f.Extensions) > 0 {
			exts = fmt.Sprintf("%v", f.Extensions)
		}
		fmt.Fprintf(w, "    %s\t(%s)\n", f.Path, exts)
	}

	// Local queue depth.
	home, _ := os.UserHomeDir()
	dbPath := filepath.Join(home, config.DefaultConfigDir, "queue.db")
	pendingCount := "-"
	deadLetterCount := "-"
	if _, err := os.Stat(dbPath); err == nil {
		q, err := queue.Open(dbPath)
		if err == nil {
			pendingCount = fmt.Sprintf("%d", q.Depth())
			deadLetterCount = fmt.Sprintf("%d", q.DeadLetterDepth())
			q.Close()
		}
	}
	fmt.Fprintf(w, "  Queue pending:\t%s\n", pendingCount)
	fmt.Fprintf(w, "  Dead letter:\t%s\n", deadLetterCount)

	// Last heartbeat time.
	heartbeatPath := filepath.Join(home, config.DefaultConfigDir, "last_heartbeat")
	if data, err := os.ReadFile(heartbeatPath); err == nil {
		fmt.Fprintf(w, "  Last heartbeat:\t%s\n", string(data))
	} else {
		fmt.Fprintf(w, "  Last heartbeat:\tnever\n")
	}

	fmt.Fprintln(w)
	return nil
}
