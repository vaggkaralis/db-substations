This folder contains helper files for enabling Android FileProvider sharing.

How to use:
- Buildozer / p4a will pick up a custom AndroidManifest template if placed in
  the project root under `android/AndroidManifest.tmpl`. The included template
  adds a `FileProvider` with authority `${applicationId}.provider` and a
  reference to `@xml/filepaths`.

- `android/res/xml/filepaths.xml` exposes the app internal `files` directory
  (so files written to `app.user_data_dir` like `change_log.txt` can be
  shared). Adjust the `<files-path>` `path` attribute if needed.

Notes:
- If you maintain a custom manifest elsewhere, merge the `<provider>` entry
  into your existing `<application>` element and include the `filepaths.xml`
  under your `res/xml` folder.
- This repository already falls back to using `Uri.fromFile()` if `FileProvider`
  is not available; however FileProvider is recommended for Android 7+.
