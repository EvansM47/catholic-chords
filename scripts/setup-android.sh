#!/usr/bin/env bash
# Setup Android APK build tools on Ubuntu/Debian (run once, needs your password for sudo).
set -e
echo "== 1. Java 17 (required by Android Gradle Plugin) =="
sudo apt update
sudo apt install -y openjdk-17-jdk unzip wget
java -version

echo "== 2. Android cmdline-tools =="
export ANDROID_SDK_ROOT="$HOME/Android/Sdk"
mkdir -p "$ANDROID_SDK_ROOT/cmdline-tools"
cd /tmp
if [ ! -f commandlinetools-linux-11076708_latest.zip ]; then
  wget -q https://dl.google.com/android/repository/commandlinetools-linux-11076708_latest.zip
fi
rm -rf "$ANDROID_SDK_ROOT/cmdline-tools/latest"
unzip -q -o commandlinetools-linux-11076708_latest.zip -d "$ANDROID_SDK_ROOT/cmdline-tools"
mv "$ANDROID_SDK_ROOT/cmdline-tools/cmdline-tools" "$ANDROID_SDK_ROOT/cmdline-tools/latest"

export PATH="$ANDROID_SDK_ROOT/cmdline-tools/latest/bin:$ANDROID_SDK_ROOT/platform-tools:$PATH"
echo "== 3. SDK packages (platform-34, build-tools, platform-tools) =="
yes | sdkmanager --licenses > /dev/null || true
sdkmanager "platform-tools" "platforms;android-34" "build-tools;34.0.0"

echo "== 4. Env vars (add to ~/.bashrc) =="
grep -q ANDROID_SDK_ROOT ~/.bashrc || cat >> ~/.bashrc <<'EOF'
export ANDROID_SDK_ROOT="$HOME/Android/Sdk"
export ANDROID_HOME="$HOME/Android/Sdk"
export PATH="$ANDROID_HOME/cmdline-tools/latest/bin:$ANDROID_HOME/platform-tools:$PATH"
export JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
EOF

echo "DONE. Restart terminal, then run: npm run android:sync && npm run android:build"
echo "SDK at: $ANDROID_SDK_ROOT"
