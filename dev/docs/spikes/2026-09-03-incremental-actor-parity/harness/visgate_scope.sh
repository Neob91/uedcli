#!/bin/bash
# How load-bearing is the span-buffer accept/subtract path? Counters over PASSING builds vs the
# failing one: `unreachable` = dropped because the zone buffer ran dry, `empty_after_test` = dropped
# by the span test itself. Both ride on the rasterizer + CopyFromRaster(Update) semantics.
cd /workspace/uedcli/.claude/worktrees/agent-a04e65a53d2fe93b0
M=/workspace/uedcli/dev/games/deusex/Maps
A=dev/docs/spikes/2026-09-03-incremental-actor-parity/harness/actor_parity.py
probe () {
  line=$(UEDCLI_VISGATE_DUMP=1 .venv/bin/python $A --dx "$1" native "$3" 2>&1 >/dev/null \
         | grep VISGATE_TRAVERSE | tail -1)
  echo "$2 N=$3 $line"
}
probe $M/06_HongKong_WanChai_Market.dx wanchai 44
probe $M/06_HongKong_WanChai_Market.dx wanchai 45
probe $M/03_NYC_UNATCOHQ.dx unatco 24
probe $M/02_NYC_Bar.dx bar 24
probe $M/01_NYC_UNATCOIsland.dx island 16
probe $M/14_OceanLab_Lab.dx oceanlab 16
echo SCOPEDONE
