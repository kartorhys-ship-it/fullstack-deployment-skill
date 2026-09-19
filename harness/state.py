"""
Checkpoint & Atomic State Management Engine
Maintains checkpoints before state transitions and executes automated rollbacks.
"""
import os
import shutil
import time
from typing import Dict, Any, List, Optional

class StateCheckpoint:
    def __init__(self, checkpoint_id: str, description: str, metadata: Dict[str, Any]):
        self.checkpoint_id = checkpoint_id
        self.description = description
        self.metadata = metadata
        self.timestamp = time.time()

class StateManager:
    def __init__(self, base_dir: str = "/tmp/mock_webapp"):
        self.base_dir = base_dir
        self.releases_dir = os.path.join(base_dir, "releases")
        self.current_link = os.path.join(base_dir, "current")
        self.previous_link = os.path.join(base_dir, "previous")
        self._checkpoints: List[StateCheckpoint] = []

    @property
    def checkpoints(self) -> List[StateCheckpoint]:
        return list(self._checkpoints)

    def create_checkpoint(self, description: str, metadata: Dict[str, Any]) -> StateCheckpoint:
        """Saves a discrete checkpoint before executing a reversible system change (T3)."""
        cp_id = f"cp_{int(time.time() * 1000)}"
        cp = StateCheckpoint(cp_id, description, metadata)
        self._checkpoints.append(cp)
        return cp

    def atomic_cutover(self, target_release_path: str) -> bool:
        """Swaps symlink current -> target_release_path atomically using ln -sfn semantics."""
        # 1. Save existing current target to previous
        if os.path.islink(self.current_link) or os.path.exists(self.current_link):
            old_target = os.readlink(self.current_link) if os.path.islink(self.current_link) else None
            if old_target:
                if os.path.islink(self.previous_link) or os.path.exists(self.previous_link):
                    try:
                        os.unlink(self.previous_link)
                    except OSError:
                        pass
                os.symlink(old_target, self.previous_link)

        # 2. Atomic switch current to target
        tmp_link = f"{self.current_link}.tmp_{int(time.time()*1000)}"
        os.symlink(target_release_path, tmp_link)
        os.replace(tmp_link, self.current_link)
        return True

    def execute_rollback(self) -> Optional[str]:
        """Rolls back current symlink to previous release if available."""
        if not os.path.islink(self.previous_link):
            return None
        previous_target = os.readlink(self.previous_link)
        self.atomic_cutover(previous_target)
        return previous_target
