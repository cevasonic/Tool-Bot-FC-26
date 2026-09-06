import unittest
import copy
from src.config import (
    set_current_step_info,
    get_current_step_info,
    set_active_workflow,
    get_active_workflow,
    set_current_step_index,
    get_current_step_index,
    add_steps_to_active_workflow
)

class TestUnassignedOption4(unittest.TestCase):
    def test_current_step_info(self):
        set_current_step_info("Open pack 'x2 Silver Players Pack'")
        self.assertEqual(get_current_step_info(), "Open pack 'x2 Silver Players Pack'")
        
        set_current_step_info("Làm SBC 'Silver Upgrade'")
        self.assertEqual(get_current_step_info(), "Làm SBC 'Silver Upgrade'")

    def test_add_steps_to_active_workflow(self):
        initial_workflow = [
            {"step": 8, "type": "open_pack", "pack_name": "x2 Silver Players Pack"},
            {"step": 14, "type": "sbc", "sbc_name": "5x 80+ Upgrade"},
            {"step": 15, "type": "open_pack", "pack_name": "5x 80+ Rare Gold Players Pack"}
        ]
        daily_state = {
            "date": "2026-09-06",
            "steps_finished": {0: True, 1: False, 2: False}
        }
        
        set_active_workflow(initial_workflow, current_idx=0)
        
        new_steps = [
            {"step": 9, "type": "sbc", "sbc_name": "Silver Upgrade"},
            {"step": 10, "type": "open_pack", "pack_name": "x3 Common Gold Players Pack"}
        ]
        
        updated_wf = add_steps_to_active_workflow(new_steps, daily_state=daily_state)
        
        # Kiểm tra độ dài workflow sau khi chèn 2 bước
        self.assertEqual(len(updated_wf), 5)
        self.assertEqual(updated_wf[0]["step"], 8)
        self.assertEqual(updated_wf[1]["step"], 9)
        self.assertEqual(updated_wf[2]["step"], 10)
        self.assertEqual(updated_wf[3]["step"], 14)
        self.assertEqual(updated_wf[4]["step"], 15)
        
        # Kiểm tra steps_finished được re-index chính xác
        finished = daily_state["steps_finished"]
        self.assertEqual(finished[0], True)   # Step 8 (đã làm)
        self.assertEqual(finished[1], False)  # Step 9 (mới thêm)
        self.assertEqual(finished[2], False)  # Step 10 (mới thêm)
        self.assertEqual(finished[3], False)  # Step 14 (dịch chuyển từ index 1)
        self.assertEqual(finished[4], False)  # Step 15 (dịch chuyển từ index 2)

    def test_step_numbers_parsing(self):
        import re
        input_str = "9, 10, 15"
        nums = [int(s) for s in re.findall(r'\d+', input_str)]
        self.assertEqual(nums, [9, 10, 15])
        
    def test_skip_step_exception_imports(self):
        import src.store
        import src.sbc
        import src.unassigned
        import main
        from src.exceptions import SkipStepException
        
        self.assertTrue(hasattr(src.store, "SkipStepException"))
        self.assertTrue(hasattr(src.sbc, "SkipStepException"))
        self.assertTrue(hasattr(main, "SkipStepException"))
        self.assertTrue(issubclass(SkipStepException, Exception))

if __name__ == "__main__":
    unittest.main()
