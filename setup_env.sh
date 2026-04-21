#!/bin/bash
# Setup environment for datasheet-parser

export JAVA_HOME="/opt/homebrew/opt/openjdk@17"
export PATH="/opt/homebrew/opt/openjdk@17/bin:$PATH"

# Add project directory to Python path if needed
# export PYTHONPATH="/path/to/datasheet-parser-new:$PYTHONPATH"

echo "Environment setup complete!"
echo "JAVA_HOME: $JAVA_HOME"
echo "Java version: $(java -version 2>&1 | head -1)"
