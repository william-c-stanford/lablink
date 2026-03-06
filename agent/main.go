// lablink-agent is the LabLink desktop file-watching agent.
//
// It monitors instrument output directories for new data files, queues them in
// a local BBolt database, and uploads them to the LabLink backend with
// automatic retry and exponential back-off.
//
// Usage:
//
//	lablink-agent register  # pair with LabLink platform (one-time)
//	lablink-agent start     # run the daemon
//	lablink-agent status    # show connectivity and queue depth
//	lablink-agent version   # print version information
package main

import "github.com/william-c-stanford/lablink/agent/cmd"

func main() {
	cmd.Execute()
}
