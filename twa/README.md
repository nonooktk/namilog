# なみログ TWA（Trusted Web Activity）パッケージング

本番 PWA `https://namilog.vercel.app` を Android アプリ（TWA）として梱包するための作業ディレクトリです。
Google 製ツール **Bubblewrap**（`@bubblewrap/cli`）を使用します。

## 前提（この Mac に導入済み）

- JDK17: `~/.bubblewrap/jdk/jdk-17.0.11+9`
- Android SDK: `~/.bubblewrap/android_sdk`（build-tools 34/35・platforms android-36・platform-tools）
- `~/.bubblewrap/config.json`（jdkPath / androidSdkPath を明示済み）
- Bubblewrap CLI はこのディレクトリにローカル導入（`./node_modules/.bin/bubblewrap`）

> ナレッジ: `01_ナレッジ/モバイル/bubblewrap-noninteractive.md`（Node v25 は非 TTY で対話プロンプトに到達するとクラッシュする。`init` は使わず、`update`/`build` を非対話フラグ付きで実行する）

## 秘匿情報（絶対にコミット・共有しない）

- `namilog.keystore` … 署名キーストア（**紛失/漏洩でアプリ更新不能・なりすまし可能**。厳重保管）
- `.keystore-env` … キーストア/キーのパスワード（ランダム生成・`chmod 600`）
- いずれも `.gitignore` 対象。ビルド成果物（`*.apk` / `*.aab` / gradle 生成物）も追跡しない。

## 再現手順

```bash
cd ~/Desktop/namilog/twa
export JAVA_HOME="$HOME/.bubblewrap/jdk/jdk-17.0.11+9/Contents/Home"
export PATH="$JAVA_HOME/bin:$PATH"
source ./.keystore-env

# Android プロジェクト生成（versionCode 自動インクリメント回避）
./node_modules/.bin/bubblewrap update --manifest=./twa-manifest.json --skipVersionUpgrade

# APK / AAB ビルド（署名は環境変数のパスワードで非対話）
./node_modules/.bin/bubblewrap build --manifest=./twa-manifest.json --skipPwaValidation
```

生成物: `app-release-signed.apk`（実機インストール用）/ `app-release-bundle.aab`（Play ストア提出用）

## Digital Asset Links

`assetlinks.json`（署名鍵の SHA-256 から生成）を本番に配置することで TWA のアドレスバー非表示・信頼関係が成立します。

- 配置先: `frontend/public/.well-known/assetlinks.json`
- 公開 URL: `https://namilog.vercel.app/.well-known/assetlinks.json`
- 署名 SHA-256: `03:D8:7A:AD:14:44:14:D9:0E:82:4F:DA:30:15:5F:4E:63:0E:D1:94:6F:A6:E5:03:B1:C2:86:4C:CF:A3:48:B7`

## メタデータ

- applicationId: `jp.namilog.app`
- appName / launcherName: `なみログ`
- versionName `1.0.0` / versionCode `1`
- themeColor `#A78BC9` / backgroundColor `#FFFBF6`
- host `namilog.vercel.app`
