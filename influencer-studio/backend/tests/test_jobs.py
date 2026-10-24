import asyncio

from studio.jobs import MAX_SKIPS, JobQueue


async def noop(job):
    return []


def test_same_model_group_runs_next_and_positions_match():
    q = JobQueue()
    first = q.submit("content", noop, group="flux2")
    q.next()  # flux2 is now loaded in ComfyUI
    talk = q.submit("talk", noop)
    image = q.submit("content", noop, group="flux2")
    dance = q.submit("dance", noop, group="wan-animate")
    image2 = q.submit("content", noop, group="flux2")
    assert first.group == "flux2" and talk.group == "talk"  # group defaults to the kind
    expected = [image, image2, talk, dance]
    assert [q.position(j) for j in expected] == [1, 2, 3, 4]
    assert [q.next()[0] for _ in expected] == expected


def test_skipped_jobs_are_not_starved():
    q = JobQueue()
    q.submit("content", noop, group="flux2")
    q.next()
    talk = q.submit("talk", noop)
    images = [q.submit("content", noop, group="flux2") for _ in range(5)]
    order = [q.position(j) for j in [talk, *images]]
    ran = [q.next()[0] for _ in range(6)]
    assert ran.index(talk) == MAX_SKIPS  # waits for at most MAX_SKIPS same-model jobs
    assert [ran.index(j) + 1 for j in [talk, *images]] == order


def test_worker_runs_jobs_and_reports_errors():
    async def scenario():
        q = JobQueue()
        worker = asyncio.create_task(q.run_forever())

        async def boom(job):
            raise RuntimeError("out of memory")

        ok, bad = q.submit("content", noop), q.submit("talk", boom)
        for _ in range(100):
            if bad.status == "error":
                break
            await asyncio.sleep(0.01)
        worker.cancel()
        return ok, bad

    ok, bad = asyncio.run(scenario())
    assert ok.status == "done" and bad.status == "error" and bad.error == "out of memory"
