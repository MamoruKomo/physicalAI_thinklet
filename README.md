# 竹迫研 ロボット：Arduino × THINKLET Cube フィジカルAI

## 最終目標

THINKLET Cubeのカメラを使い、Arduino（basic robokit2）のアームを動かすフィジカルAIを作る。
最初のアプリは、カメラ映像が明るいとアームが上がり、暗いと下がる構成。
現段階の判断は平均輝度としきい値によるルールで、学習済みAIモデルは使っていない。

## アプリの構成

`THINKLETのカメラ → USB/ADB → Macの明暗判定 → USBシリアル → Arduinoのアーム`

- `thinklet/`：Camera2でカラー映像と平均輝度を取得するAndroidアプリ。露出固定・再調整に対応。
- `bridge/`：Mac上で動く中継と制御。しきい値・切替幅・平滑化、手動／自動切替、通信断での停止。
- `dashboard/`：ライブ映像、明るさのグラフ、接続、制御判断、角度指令、状態記録を表示する操作ボード。
- `arduino/brightness_arm/`：位置制御サーボ用の暫定ファームウェア。公式Servoライブラリを使用。

アームの実位置は位置センサーがなければ計測できないため、ボードは出力指令と目標角度を表示する。
basic robokit2の正式な製品仕様と今回の配線は確認中。アーム動作の実機検証は未完了。

## 起動

Android SDKとJDK 17、Python 3.12、ADBを使用する。追加のPythonパッケージは不要。
SDKの既定パスはmacOS用。別の環境では `ANDROID_HOME` と `JAVA_HOME` を指定する。

```sh
# 初回のみ、config/devices.example.json を devices.local.json にコピーして実機の値を設定
python3 scripts/build_camera.py
python3 scripts/connect_camera.py --install
python3 -m bridge.server
```

[操作ボードを開く](http://127.0.0.1:8766)。次回以降は `--install` を省略できる。
THINKLETで別のアプリへ移動するとカメラ取得を止め、アーム制御も停止する。
ボードの再起動・カメラ復帰で自動制御を再開することはない。

アーム接続前に [ハードウェア確認](docs/HARDWARE.md)を行う。
Arduinoには専用ファームウェアが必要。配線確認・制御有効化・自動連動はそれぞれ明示的に操作する。

## 検証

```sh
python3 -m unittest discover -v
arduino-cli core install arduino:avr@1.8.8
arduino-cli lib install Servo@1.3.0
arduino-cli compile --fqbn arduino:avr:uno arduino/brightness_arm
```

GitHub Actionsでも制御テストとUno用ファームウェアのコンパイルを行い、HEXを成果物として保存する。
実機の結果と未完了項目は [検証記録](docs/VALIDATION.md)に記載する。

## ファイル管理

[GitHub: MamoruKomo/physicalAI_thinklet](https://github.com/MamoruKomo/physicalAI_thinklet)でコード・設計・検証記録を管理する。
機器固有のシリアルやローカル設定は `config/devices.local.json` に保存し、Gitには含めない。
認証情報・APIキーはGitに含めない。

## 接続確認（2026-10-07・日本時間）

| 対象 | Macで確認した状態 |
| --- | --- |
| Arduino / basic robokit2 | USB認識あり。Arduino / Generic CDC、VID:PID `2341:0043`、シリアルポート `/dev/cu.usbmodem1101`。 |
| THINKLET Cube | USB認識あり。QUALCOMM / SDM450-QRD、VID:PID `05c6:90b8`。 |
| THINKLET Cubeの開発用ADB通信 | 接続成功。対象シリアルを指定した `adb get-state` は `device`。モデル `THINKLET LC02`、Android `8.1.0`、Fairy OS `15.000.0`。対象を指定した `getprop` の応答を確認。 |
| ArduinoとTHINKLET Cube間の通信・動作 | 未確認。Macに両機器が接続されていることと、両機器間の連携は別の検証。 |

2026-10-07 16:46（日本時間）にTHINKLET Cubeを再確認。USBのVID:PIDと機器シリアルがローカル設定に一致し、対象シリアルを指定した `adb get-state` は `device`。`adb shell` の確認文字列、モデル `THINKLET LC02`、Android `8.1.0`、起動完了状態 `sys.boot_completed=1` の応答を確認した。この再確認ではArduinoおよび両機器間の連携動作は検証していない。

同日、ローカル設定の対象シリアルを指定してscrcpy `3.3.4`で画面表示を開始した。通常接続は画面表示前に失敗したため、`--force-adb-forward --no-audio --window-title 'THINKLET Cube'` を使用。サーバー接続、Metal描画、映像サイズ `1080x1920` のログを確認した。Arduinoとの連携動作は未検証。

## 次の確認

1. basic robokit2の公式製品ページ・制御方式・配線・可動範囲を確認する。
2. アーム用ファームウェアを実機へ書き込み、明暗に応じた上下動を検証する。
3. 実機動作と画面表示の一致を確認し、その後に画像認識や学習モデルへ拡張する。

ADB操作時は対象シリアルを必ず指定する。

## 公式資料

- [THINKLETの起動とUSB接続](https://fairydevicesrd.github.io/thinklet.app.developer/docs/startGuide/useCamera/)
- [THINKLET Cube開発ガイドライン](https://fairydevicesrd.github.io/thinklet.app.developer/docs/devGuide/thinkletCube/)
- [THINKLET Cube LC-02取扱説明書](https://static-connected-worker.thinklet.fd.ai/support/tl-cube/ja/)
