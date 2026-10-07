# プロジェクト方針

- 最終目標は、Arduino（basic robokit2）とTHINKLET Cubeを連携したフィジカルAIの構築。
- ファイル管理先は公開リポジトリ `MamoruKomo/physicalAI_thinklet`。コード・設計・検証記録をここで管理する。
- 機器固有のシリアルはGit管理対象外の `config/devices.local.json` を参照する。認証情報・APIキー・個人情報をコミットしない。
- ADB操作では対象シリアルを明示する。USB認識、ADB通信、両機器間の連携動作を区別して検証結果を記録する。
