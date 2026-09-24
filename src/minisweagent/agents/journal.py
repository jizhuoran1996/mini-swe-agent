"""The default agent loop with incremental, artifact-backed trajectory storage."""

from __future__ import annotations

import json
from pathlib import Path

from minisweagent.agents.default import DefaultAgent
from minisweagent.utils.replay_store import without_secrets


class JournalAgent(DefaultAgent):
    def __init__(self, model, env, **kwargs):
        super().__init__(model, env, **kwargs)
        self.store, self.episode_id = model.store, model.episode_id
        self.message_refs: list[str] = []
        self.save(None)

    def add_messages(self, *messages: dict) -> list[dict]:
        compact = []
        for message in messages:
            item = dict(message)
            if "extra" in item:
                item["extra"] = dict(item["extra"])
                if "raw_output" in item["extra"]:
                    item["extra"]["raw_output_ref"] = self.store.put_text(item["extra"].pop("raw_output"))
            reference = self.store.put(item)
            self.store.event(self.episode_id, "message", {"index": len(self.message_refs), "ref": reference})
            self.message_refs.append(reference)
            compact.append(item)
        return super().add_messages(*compact)

    def run(self, task: str = "", **kwargs) -> dict:
        if self.message_refs:
            raise ValueError("Create a fresh model and episode for each agent task")
        return super().run(task, **kwargs)

    def save(self, path: Path | None, *extra_dicts) -> dict:
        data = self.serialize(*extra_dicts)
        data.pop("messages")
        data = without_secrets(data)
        data.update(
            trajectory_format="mini-swe-agent-index-1",
            store_path=str(self.store.path),
            episode_id=self.episode_id,
            message_refs=list(self.message_refs),
        )
        metadata = self.store.metadata(self.episode_id)
        metadata["trajectory"] = data
        self.store.update_metadata(self.episode_id, metadata)
        if path:
            path = Path(path)
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_name(path.name + ".tmp")
            temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2))
            temporary.replace(path)
        return data
