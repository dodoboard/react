import time

from studio.store import Store
from tests.conftest import wait_job

SPEC = {"age": 25, "selections": {"gender": {"values": ["woman"]}}}


def generate(client):
    return client.post("/api/builder/generate", json={"spec": SPEC, "count": 1}).json()


def test_finished_jobs_are_listed_and_survive_a_restart(client, tmp_path):
    job = wait_job(client, generate(client))
    listed = client.get("/api/jobs").json()
    assert listed[0]["id"] == job["id"] and listed[0]["status"] == "done"
    store = client.app.state.studio.store
    saved = store.job(job["id"])
    assert saved["status"] == "done" and saved["outputs"][0]["id"] == job["outputs"][0]["id"]


def test_unfinished_jobs_are_marked_after_a_restart(tmp_path):
    store = Store(tmp_path)

    class Job:  # what JobQueue hands to persist
        id, kind, status, progress, error, outputs, created_at = "j1", "talk", "running", 0.4, None, [], time.time()

    store.save_job(Job)
    store.close()
    again = Store(tmp_path)
    assert again.job("j1")["status"] == "error" and again.job("j1")["error"] == "Studio restarted"


def test_cancel_queued_and_running_jobs(client, fake_comfy):
    fake_comfy.app.state.slow = 0.3  # each sampling step takes a while
    first, second = generate(client), generate(client)
    deadline = time.monotonic() + 10
    while client.get(f"/api/jobs/{first['id']}").json()["status"] != "running":
        assert time.monotonic() < deadline
        time.sleep(0.05)
    queued = client.delete(f"/api/jobs/{second['id']}").json()
    assert queued["status"] == "cancelled"
    client.delete(f"/api/jobs/{first['id']}")
    running = wait_job(client, client.get(f"/api/jobs/{first['id']}").json())
    assert running["status"] == "cancelled" and fake_comfy.app.state.interrupts == 1
    assert fake_comfy.app.state.deleted  # the prompt was also dropped from ComfyUI's queue
    fake_comfy.app.state.slow = 0
    assert wait_job(client, generate(client))["status"] == "done"  # the worker keeps going
    assert client.delete("/api/jobs/nope").status_code == 404


def test_outdated_comfyui_is_reported_per_mode(client, fake_comfy):
    assert client.get("/api/health").json()["missing_nodes"] == []
    assert client.get("/api/motion/health").json()["nodes"]["talk"] == []
    fake_comfy.app.state.missing_nodes = {"WanInfiniteTalkToVideo", "Flux2Scheduler"}
    client.app.state.studio.comfy._object_info = None  # the cache lives until ComfyUI is updated
    assert client.get("/api/health").json()["missing_nodes"] == ["Flux2Scheduler"]
    nodes = client.get("/api/motion/health").json()["nodes"]
    assert nodes["talk"] == ["WanInfiniteTalkToVideo"] and nodes["dance"] == []
    assert client.get("/api/voice/health").json()["missing_nodes"] == ["WanInfiniteTalkToVideo"]
