import copy
import unittest
from uuid import UUID

from pydantic import ValidationError

from app.schemas.result_flow import ResultFlow


def flow_payload():
    return {
        "schema_version": 1,
        "steps": [
            {
                "id": str(UUID(int=1)), "sequence": 1, "type": "DRAWER",
                "input_step_id": None, "status": "SUCCEEDED",
                "created_at": "2026-09-07T00:00:00Z",
                "output": {
                    "type": "TIMING", "content_type": "WAVEDROM",
                    "content": {"signal": []}, "render_artifact_id": str(UUID(int=10)),
                    "summary": "Initial extraction", "changes": [],
                },
            },
            {
                "id": str(UUID(int=2)), "sequence": 2, "type": "VERIFY",
                "input_step_id": str(UUID(int=1)), "status": "SUCCEEDED",
                "created_at": "2026-09-07T00:01:00Z",
                "output": {
                    "match": "TRUE", "summary": "Matches source",
                    "diff_count": 0, "diffs": [], "suggestions": [],
                },
            },
        ],
        "final_drawer_step_id": str(UUID(int=1)),
        "final_verify_step_id": str(UUID(int=2)),
    }


class ResultFlowTest(unittest.TestCase):
    def test_accepts_drawer_verify_pair(self):
        flow = ResultFlow.model_validate(flow_payload())
        self.assertEqual(flow.steps[0].output.content, {"signal": []})
        self.assertEqual(flow.steps[1].output.match, "TRUE")

    def test_accepts_second_drawer_verify_cycle(self):
        payload = flow_payload()
        second = copy.deepcopy(payload["steps"])
        for index, step in enumerate(second, start=3):
            step.update(id=str(UUID(int=index)), sequence=index,
                        input_step_id=str(UUID(int=index - 1)))
        payload["steps"].extend(second)
        payload.update(final_drawer_step_id=str(UUID(int=3)),
                       final_verify_step_id=str(UUID(int=4)))
        self.assertEqual(len(ResultFlow.model_validate(payload).steps), 4)

    def test_rejects_verify_pointing_to_wrong_input(self):
        payload = flow_payload()
        payload["steps"][1]["input_step_id"] = str(UUID(int=99))
        with self.assertRaises(ValidationError):
            ResultFlow.model_validate(payload)

    def test_rejects_incorrect_output_type(self):
        payload = flow_payload()
        payload["steps"][1]["output"] = payload["steps"][0]["output"]
        with self.assertRaises(ValidationError):
            ResultFlow.model_validate(payload)

    def test_rejects_diff_count_mismatch(self):
        payload = flow_payload()
        payload["steps"][1]["output"].update(match="FALSE", diff_count=1)
        with self.assertRaises(ValidationError):
            ResultFlow.model_validate(payload)

    def test_partial_is_successful_verification_execution(self):
        payload = flow_payload()
        payload["steps"][1]["output"].update(match="PARTIAL", diff_count=1, diffs=None)
        flow = ResultFlow.model_validate(payload)
        self.assertEqual(flow.steps[1].status, "SUCCEEDED")
        self.assertEqual(flow.steps[1].output.match, "PARTIAL")

    def test_rejects_pending_step_with_output(self):
        payload = flow_payload()
        payload["steps"][1]["status"] = "RUNNING"
        with self.assertRaises(ValidationError):
            ResultFlow.model_validate(payload)

    def test_rejects_final_verify_without_final_drawer(self):
        payload = flow_payload()
        payload["final_drawer_step_id"] = None
        with self.assertRaises(ValidationError):
            ResultFlow.model_validate(payload)

    def test_accepts_running_snapshot_without_final_selection(self):
        payload = flow_payload()
        payload["steps"][1].update(status="RUNNING", output=None)
        payload.update(final_drawer_step_id=None, final_verify_step_id=None)
        self.assertIsNone(ResultFlow.model_validate(payload).final_verify_step_id)


if __name__ == "__main__":
    unittest.main()
