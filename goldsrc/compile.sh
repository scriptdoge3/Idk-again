#!/bin/sh
# Compile Sable Creek with SDHLT / VHLT on Linux. TOOLS = folder with the compile tools.
set -e
TOOLS=${TOOLS:-$HOME/sdhlt/tools}
cd "$(dirname "$0")/out"
"$TOOLS/sdHLCSG" -wadinclude sablecreek sablecreek
"$TOOLS/sdHLBSP" sablecreek
"$TOOLS/sdHLVIS" -full sablecreek
"$TOOLS/sdHLRAD" -extra -lights lights.rad sablecreek
echo "Done: out/sablecreek.bsp"
