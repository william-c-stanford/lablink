# SDL Software Frameworks: Detailed Comparison

## Framework Comparison Matrix

| Framework | Language | License | Architecture | Maturity | Lab Deployed? |
|-----------|----------|---------|-------------|----------|---------------|
| **AlabOS** | Python | Open-source | Manager-worker, MongoDB, graph workflows | Production | Yes (A-Lab, LBNL, 2500+ samples) |
| **UniLabOS** | Python | Open-source | A/R/A&R model, edge-cloud, CRUTD protocol | v1.0 (Dec 2025) | Yes (DeepModeling labs) |
| **IvoryOS** | Python | Open-source | Auto-generated web UI, drag-and-drop workflows | Published (Nature Comms) | Academic |
| **Chemspeed/SciY SDL** | Proprietary | Commercial | Open backbone, FAIR data, vendor-agnostic | Announced (SLAS 2026) | Enterprise pilot |
| **HELAO** | Python | Open-source | Hierarchical orchestration | Published | Electrochemistry SDLs |
| **ChemOS** | Python | Open-source | Optimization + robotic execution | Published | Academic |

## AlabOS Deep Dive

### Architecture Components
1. **Dashboard Server** - Web UI + monitoring APIs
2. **Experiment Manager** - Transforms high-level requests into tasks
3. **Task Manager** - Launches/monitors task actors (separate processes)
4. **Resource Manager** - Assigns/tracks available lab resources
5. **MongoDB Backend** - Flexible schema for heterogeneous data

### Workflow Model
- Graph-based: tasks = nodes, dependencies = edges
- Reconfigurable: workflows can be modified at runtime
- Concurrent: multiple workflows execute simultaneously
- Resource-aware: reservation mechanism prevents conflicts

### Key Lesson for LabLink
AlabOS separates "what to do" (workflow graph) from "how to do it" (task actors) from "with what" (resource manager). LabLink should similarly separate data concerns from orchestration concerns.

## UniLabOS Deep Dive

### A/R/A&R Model
Every lab element is classified as:
- **Action (A)**: Something that can be done (e.g., "mix", "heat", "measure")
- **Resource (R)**: Something that can be used (e.g., a sample, a reagent, an instrument)
- **Action&Resource (A&R)**: Something that is both (e.g., a robot arm that IS a resource but also PERFORMS actions)

### Dual Topology
1. **Logical ownership**: Which module "owns" which instruments/samples
2. **Physical connectivity**: How instruments are physically connected (tubes, conveyors, etc.)

### CRUTD Protocol
Extends CRUD with Transfer (T) for physical material movement:
- **Create**: New sample, new experiment
- **Read**: Query state
- **Update**: Modify digital state
- **Transfer**: Move physical material between locations
- **Delete**: Decommission (with audit)

### Protocol Support
UniLabOS abstracts over: Modbus, PLC, ROS 2, OPC UA, TCP/IP, SiLA 2

### Key Lesson for LabLink
The distinction between logical and physical topology is brilliant. LabLink should capture both "what instruments does this lab have?" (logical) and "how are they physically connected?" (physical) -- even if only the logical topology matters for V1.

## Multi-Agent Lab Frameworks

### MARS (Multi-Agent Robotic System)
- 19 LLM agents, 16 domain tools
- Functional modules: planning, synthesis, characterization, analysis
- Each agent is specialized but can communicate with others
- Orchestrator coordinates the overall workflow

### ChemAgents
- Hierarchical: Task Manager at top
- 4 specialized agents:
  - Literature Reader (searches papers)
  - Experiment Designer (plans experiments)
  - Computation Performer (runs simulations)
  - Robot Operator (controls instruments)

### k-agents
- Knowledge agents: encode lab knowledge (SOPs, methods)
- Execution agents: break procedures into state machines
- Translation agents: convert to instrument commands
- Inspection agents: analyze results, decide next steps

### Key Lesson for LabLink
The pattern is consistent: **specialized agents communicate through a shared data layer**. LabLink IS that shared data layer. Don't try to be the orchestrator; be the knowledge backbone.
