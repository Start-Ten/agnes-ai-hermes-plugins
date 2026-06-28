# Agnes AI Hermes Plugins

Hermes Agent plugins for free multimodal AI generation using [Agnes AI](https://agnes-ai.com).

## Plugins

- `image_gen/agnes` — Image generation (Agnes Image 2.1 Flash)
- `video_gen/agnes` — Video generation (Agnes Video V2.0)

## Setup

```bash
cp -r image_gen $HERMES_HOME/plugins/
cp -r video_gen $HERMES_HOME/plugins/
echo 'AGNES_API_KEY=your_key_here' >> $HERMES_HOME/.env
hermes plugins enable image_gen/agnes
hermes plugins enable video_gen/agnes
```

## API

- Base URL: `https://apihub.agnes-ai.com/v1`
- Get API key: [platform.agnes-ai.com](https://platform.agnes-ai.com)
- All models **free** indefinitely

## License

MIT
