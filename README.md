# Catholic Chords

An offline-first Catholic hymn and prayer app with Mass planning and choir collaboration features.

## Run locally

Install Node.js, then run:

```sh
npm install
npm run dev
```

## Build Android

Generate and sync the web bundle, then build the Android debug APK:

```sh
npm run www:sync
npm run android:build
```

The APK is written to `android/app/build/outputs/apk/debug/app-debug.apk`.

The Android application ID is `org.vrcthika.choirhymns`. Release signing keys are local secrets and must not be committed to this repository.

## Content and attributions

The app contains hymn and prayer texts attributed in the app to their respective printed sources, plus song references from Sauti za Kuimba. Those texts and third-party artwork may have rights separate from the application code. See the app's Credits & Sources section for attribution details.
