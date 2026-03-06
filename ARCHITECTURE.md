Main Architecture
=================

*   Frontend Input
    
    *   Select local data sets
        
    *   Configure 
        
    *   Click Run Simulation
        
*   Backend Processing Pipeline:
    
    *   Local AI Processing → AI Event Timeline
        
    *   Mesh Network Simulation
        
    *   Log Analysis
        
*   Frontend Output
    
    *   View Mesh Network Graph
        
    *   Replayable AI Event timeline
        
    *   Dashboard Summary of Logs
        

Technical Detail of Pipeline
============================

**React App**
-------------

Users select local datasets, configure scenarios and mesh networks, and click Run Simulation.

**Outputs: locations of local datasets, and scenario configuration.**

**Local AI Processing**
-----------------------

First, standardize input datasets and slice into inference-ready windows for preparation to feed into the models.

*   Normalize sample rate of datasets
    
*   Convert to proper format
    
*   Slice into sliding 3-second windows
    

Then, feed into and run the PyTorch inference model based on the user’s selected configuration. 

Using pre-collected benchmark tables from ESP32 and Radxa runs, latency and energy values are estimated per inference event.

**Output: AI detections and their associated timestamps, latency, and energy metrics.**

**Mesh Network Simulation**
---------------------------

The next step is to simulate how these detections will feed into a simulate routing, congestion, and other metrics and output the Structured Simulation Log in JSON.

Network:

*   Packet generation
    
*   Congestion
    
*   Retries
    
*   Routing
    
*   Transmission latency
    

Power:

*   Energy per event
    
*   Idle consumption
    

**Output:**

```json
[{ "event": "transmission",  "node": "node\_03",  "timestamp": 15432,  "packet\_status": "retry" }, ...\]
```

**Log Interpretation & Analysis**
---------------------------------

Using the Structured Simulation Log, compute metrics and analyses for the dashboard.

Metrics:

*   Battery lifetime
    
*   Network Congestion
    
*   AI throughput
    
*   Event delivery success
    

**Output: Clean, dashboard ready output logs and charts**

**Dashboards**
--------------

Visualizations are viewed through the dashboards on the React app.

Charts:

*   Mesh graph visualization
    
*   Battery life graphs
    
*   AI performance scorecards
    

The System Architecture
=======================

**Frontend (React)**
--------------------

*   Select local file paths
    
*   Configure simulation
    
*   Monitor status
    
*   View results
    

**Backend (FastAPI)**
---------------------

*   User authentication
    
*   Local AI Processing
    
*   Mesh Network Simulation
    
*   Log Interpretation and Analysis
