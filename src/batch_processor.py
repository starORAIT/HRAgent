from datetime import datetime
import logging
from db_manager import ProcessingBatch, beijing_now

def create_batch_record(db, total_count):
    """创建批次记录"""
    batch = ProcessingBatch(
        batch_id=f"batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        total_count=total_count,
        start_time=beijing_now()
    )
    db.add(batch)
    db.commit()
    return batch

def update_batch_status(db, batch, results):
    """更新批次处理状态"""
    try:
        batch.processed_count = batch.total_count
        batch.success_count = len([r for r in results if r is not None])
        batch.failed_count = batch.total_count - batch.success_count
        batch.end_time = beijing_now()
        batch.status = "COMPLETED"
        db.commit()
    except Exception as e:
        logging.error(f"更新批次状态失败: {e}")
        batch.status = "FAILED"
        db.commit()
