import sys
import re

with open('models/printer.py', 'r', encoding='utf-8') as f:
    c = f.read()

# Fix 1: During RUNNING
c = c.replace(
    'active_key = getattr(self, "_current_job_slot_key", None) or self.get_active_spool_key()',
    'active_key = getattr(self, "_current_job_slot_key", None) or self.get_active_spool_key() or getattr(self, "last_active_slot", None)',
    1
)

# Fix 2: During FINISH
old_block = """                        if self._current_job_grams > 0:
                            active_key = getattr(self, "_current_job_slot_key", None) or self.get_active_slot_key()
                            old_w = self.get_slot_grams(active_key)
                            final_weight = self._current_job_grams
                            new_w = max(0.0, round(old_w - final_weight, 2))
                            self.set_slot_grams(new_w, active_key)
                            self._job_deducted = True
                            self.last_job_grams = final_weight
                            self._deduct_spool_warehouse(active_key, final_weight)
                            logger.info(
                                f"🏁 Auto-deducted {final_weight}g from AMS Slot {active_key} for [{self.name}] on job completion. Old: {old_w}g -> New: {new_w}g"
                            )
                            self._trigger_save()"""

new_block = """                        if self._current_job_grams > 0:
                            active_key = getattr(self, "_current_job_slot_key", None) or self.get_active_spool_key() or getattr(self, "last_active_slot", None)
                            if active_key is None and not getattr(self, "has_ams", False):
                                active_key = "254"
                            
                            if active_key is None:
                                logger.warning(f"[{self.name}] Cannot auto-deduct filament on FINISH: active slot unknown (bot likely restarted).")
                            else:
                                old_w = self.get_slot_grams(active_key)
                                final_weight = self._current_job_grams
                                new_w = max(0.0, round(old_w - final_weight, 2))
                                self.set_slot_grams(new_w, active_key)
                                self._job_deducted = True
                                self.last_job_grams = final_weight
                                self._deduct_spool_warehouse(active_key, final_weight)
                                logger.info(
                                    f"🏁 Auto-deducted {final_weight}g from AMS Slot {active_key} for [{self.name}] on job completion. Old: {old_w}g -> New: {new_w}g"
                                )
                                self._trigger_save()"""

c = c.replace(old_block, new_block)

with open('models/printer.py', 'w', encoding='utf-8') as f:
    f.write(c)
