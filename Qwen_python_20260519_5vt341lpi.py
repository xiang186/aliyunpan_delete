#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
阿里云盘重复文件清理工具 - v3.0 (完美适配 aligo 6.2+)
依赖: pip install aligo>=6.0
"""
import sys
import time
import logging
from collections import defaultdict
from aligo import Aligo

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

def init_client():
    """初始化客户端"""
    try:
        client = Aligo()
        user = client.get_user()
        if not user or not getattr(user, 'user_id', None):
            logger.error("登录验证失败")
            sys.exit(1)
        logger.info(f"✅ 登录成功: {getattr(user, 'nick_name', '用户')}")
        return client
    except Exception as e:
        logger.error(f"初始化失败: {e}")
        sys.exit(1)

def scan_all_files(client):
    """递归扫描所有文件（兼容 aligo 6.x 返回值）"""
    files = []
    
    def _scan(parent_id="root", depth=0):
        marker = None
        while True:
            try:
                # 🔄 aligo 6.x: 返回 (list[File], next_marker|None)
                result = client.get_file_list(
                    parent_file_id=parent_id,
                    marker=marker,
                    limit=200,
                    all=False  # ⚠️ 必须设为 False，否则无法手动分页
                )
                
                # ✅ 兼容新旧版本返回值
                if isinstance(result, tuple) and len(result) == 2:
                    file_list, next_marker = result
                elif hasattr(result, 'items'):
                    file_list, next_marker = result.items, getattr(result, 'next_marker', None)
                else:
                    file_list, next_marker = result or [], None
                
                for f in file_list:
                    if f.type == "file":
                        files.append(f)
                    elif f.type == "folder":
                        _scan(f.file_id, depth+1)
                        time.sleep(0.05)
                
                if not next_marker:
                    break
                marker = next_marker
                time.sleep(0.15)  # 防限流
                
            except Exception as e:
                logger.warning(f"扫描目录 {parent_id} 失败: {e}")
                break
    
    logger.info("开始扫描文件...")
    _scan()
    logger.info(f"✅ 扫描完成，共发现 {len(files)} 个文件")
    return files

def find_duplicates(files):
    """基于 content_hash/sha1 + size 识别重复"""
    hash_map = defaultdict(list)
    skipped = 0
    
    for f in files:
        # aligo 6.x 使用 content_hash 替代 sha1
        file_hash = getattr(f, 'content_hash', None) or getattr(f, 'sha1', None)
        size = getattr(f, 'size', None)
        
        if not file_hash or not size:
            skipped += 1
            continue
        key = (file_hash, size)
        hash_map[key].append(f)
    
    if skipped:
        logger.info(f"⚠️ 跳过 {skipped} 个无哈希/无大小的文件")
    
    dup_groups = {k: v for k, v in hash_map.items() if len(v) > 1}
    logger.info(f"🔍 发现 {len(dup_groups)} 组重复文件")
    return dup_groups

def select_files_to_delete(dup_groups, strategy="oldest"):
    """选择待删除文件"""
    to_delete = []
    
    for key, group in dup_groups.items():
        if strategy == "largest":
            sorted_group = sorted(group, key=lambda x: getattr(x, 'size', 0), reverse=True)
        else:  # oldest/newest
            sorted_group = sorted(
                group,
                key=lambda x: getattr(x, 'created_at', 0) or getattr(x, 'created_time', 0) or 0,
                reverse=(strategy == "newest")
            )
        
        # 保留第一个，删除其余
        for f in sorted_group[1:]:
            to_delete.append(f)
    
    logger.info(f"📋 将保留 {len(dup_groups)} 个文件，标记 {len(to_delete)} 个待删除")
    return to_delete

def delete_files(client, files_to_delete, dry_run=True, delay=0.5):
    """执行删除（移入回收站）"""
    success = fail = 0
    
    for f in files_to_delete:
        name = getattr(f, "name", "unknown")
        
        if dry_run:
            logger.info(f"[DRY RUN] 准备删除: {name}")
            continue
        
        try:
            # aligo 6.x 推荐使用 move_file_to_trash
            if hasattr(client, 'move_file_to_trash'):
                client.move_file_to_trash(file_id=f.file_id)
            elif hasattr(client, 'delete_file'):
                client.delete_file(file_id=f.file_id)
            else:
                raise AttributeError("No delete method found")
                
            logger.info(f"✅ 已删除: {name}")
            success += 1
        except Exception as e:
            logger.error(f"❌ 删除失败 {name}: {e}")
            fail += 1
        
        time.sleep(delay)
    
    if not dry_run:
        logger.info(f"🎯 删除完成: 成功 {success}, 失败 {fail}")

def main():
    logger.info("🗂️ 阿里云盘重复文件清理工具 v3.0 (aligo>=6.2)")
    client = init_client()
    
    # 1. 扫描
    all_files = scan_all_files(client)
    if not all_files:
        logger.warning("⚠️ 未找到任何文件，退出")
        return
    
    # 2. 识别重复
    dup_groups = find_duplicates(all_files)
    if not dup_groups:
        logger.info("🎉 未发现重复文件")
        return
    
    # 3. 选择策略
    print("\n📌 保留策略:")
    print("  [1] oldest  - 保留最早创建（默认）")
    print("  [2] newest  - 保留最新创建")
    print("  [3] largest - 保留体积最大")
    
    choice = input("请输入选项 (1/2/3, 默认 1): ").strip()
    strategy_map = {"1": "oldest", "2": "newest", "3": "largest", "": "oldest"}
    strategy = strategy_map.get(choice, "oldest")
    
    to_delete = select_files_to_delete(dup_groups, strategy)
    
    # 4. 预览 + 确认
    print(f"\n📊 待删除文件预览 (前 10 个):")
    for f in to_delete[:10]:
        size_mb = getattr(f, 'size', 0) / 1024 / 1024
        print(f"  • {getattr(f, 'name', 'unknown')} ({size_mb:.2f}MB)")
    if len(to_delete) > 10:
        print(f"  ... 还有 {len(to_delete)-10} 个文件")
    
    dry_run = input("\n🔒 是否仅模拟运行？(y/n, 默认 y): ").strip().lower() != "n"
    
    if dry_run:
        delete_files(client, to_delete, dry_run=True)
        logger.info("\n✅ 模拟结束，未执行删除。确认无误后重新运行并输入 'n'。")
    else:
        confirm = input("\n⚠️  警告：文件将移入回收站（30天后清空）。输入 'yes' 确认: ").strip().lower()
        if confirm == "yes":
            delete_files(client, to_delete, dry_run=False)
            logger.info("✅ 清理完成！请前往网页版回收站核对。")
        else:
            logger.info("❌ 操作已取消。")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("\n👋 用户中断，安全退出")
    except Exception as e:
        logger.exception(f"💥 未捕获异常: {e}")