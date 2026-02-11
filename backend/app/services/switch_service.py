from typing import List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, or_
from sqlalchemy.orm import selectinload

from app.models.switch import Switch
from app.models.alert import Alert
from app.models.mac_history import MacHistory
from app.models.mac_location import MacLocation
from app.models.topology_link import TopologyLink
from app.models.discovery_log import DiscoveryLog
from app.models.port import Port
from app.schemas.switch import DeleteResult


class SwitchService:
    @staticmethod
    async def delete_switches_bulk(db: AsyncSession, switch_ids: List[int]) -> DeleteResult:
        """
        Delete switches and all related data in cascade order
        """
        deleted_count = 0

        async with db.begin():
            # Verify switches exist and count them
            result = await db.execute(
                select(Switch).where(Switch.id.in_(switch_ids))
            )
            switches = result.scalars().all()
            actual_count = len(switches)

            if actual_count == 0:
                return DeleteResult(deleted_count=0, success=True)

            # Cascade delete in correct order to avoid foreign key violations
            # 1. Alerts (references switch_id, port_id)
            await db.execute(
                delete(Alert).where(
                    or_(
                        Alert.switch_id.in_(switch_ids),
                        Alert.port_id.in_([port.id for switch in switches for port in switch.ports])
                    )
                )
            )

            # 2. MacHistory (references switch_id, port_id)
            await db.execute(
                delete(MacHistory).where(
                    or_(
                        MacHistory.switch_id.in_(switch_ids),
                        MacHistory.port_id.in_([port.id for switch in switches for port in switch.ports])
                    )
                )
            )

            # 3. MacLocations (references switch_id, port_id)
            await db.execute(
                delete(MacLocation).where(
                    or_(
                        MacLocation.switch_id.in_(switch_ids),
                        MacLocation.port_id.in_([port.id for switch in switches for port in switch.ports])
                    )
                )
            )

            # 4. TopologyLinks (references local_switch_id, remote_switch_id)
            await db.execute(
                delete(TopologyLink).where(
                    or_(
                        TopologyLink.local_switch_id.in_(switch_ids),
                        TopologyLink.remote_switch_id.in_(switch_ids)
                    )
                )
            )

            # 5. DiscoveryLogs (references switch_id)
            await db.execute(
                delete(DiscoveryLog).where(DiscoveryLog.switch_id.in_(switch_ids))
            )

            # 6. Ports (references switch_id)
            await db.execute(
                delete(Port).where(Port.switch_id.in_(switch_ids))
            )

            # 7. Switches
            await db.execute(
                delete(Switch).where(Switch.id.in_(switch_ids))
            )

            deleted_count = actual_count

        return DeleteResult(deleted_count=deleted_count, success=True)

    @staticmethod
    async def delete_all_switches(db: AsyncSession) -> DeleteResult:
        """
        Delete all switches and all related data
        """
        # Get count before deletion
        result = await db.execute(select(Switch))
        total_switches = len(result.scalars().all())

        if total_switches == 0:
            return DeleteResult(deleted_count=0, success=True)

        # Use the same cascade logic as bulk delete
        return await SwitchService.delete_switches_bulk(db, [switch.id for switch in result.scalars().all()])