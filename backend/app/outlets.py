"""The plugs configured in config/outlets.yaml, kept in sync with the database."""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .billing import ConfigError, _read_yaml
from .db import Outlet


class OutletConfig(BaseModel):
    """One entry of outlets.yaml."""

    # A misspelled key (e.g. `modle`) is an error instead of being silently ignored.
    model_config = ConfigDict(extra="forbid", frozen=True)

    slug: str = Field(min_length=1)
    name: str = Field(min_length=1)
    ip: str = Field(min_length=1)
    model: Literal["p110", "p115"] = "p110"


@dataclass(frozen=True)
class OutletInfo:
    """A configured plug together with its database id."""

    id: int
    slug: str
    name: str
    ip: str
    model: str


def load_outlets(config_dir: Path) -> list[OutletConfig]:
    path = config_dir / "outlets.yaml"
    data = _read_yaml(path)
    entries = data.get("outlets") if isinstance(data, dict) else None
    if not entries:
        raise ConfigError(f"{path}: expected a non-empty 'outlets' list")

    outlets: list[OutletConfig] = []
    for i, entry in enumerate(entries):
        try:
            outlets.append(OutletConfig.model_validate(entry))
        except ValidationError as exc:
            raise ConfigError(f"{path} outlets[{i}]: {exc}") from exc

    slugs = [outlet.slug for outlet in outlets]
    for slug in set(slugs):
        if slugs.count(slug) > 1:
            raise ConfigError(f"{path}: duplicated slug '{slug}'")
    return outlets


async def sync_outlets(
    session_factory: async_sessionmaker[AsyncSession], configs: list[OutletConfig]
) -> list[OutletInfo]:
    """Create or update the database rows of the configured outlets, in config order.

    Outlets removed from the YAML are left in the database: they have history.
    """
    infos: list[OutletInfo] = []
    async with session_factory() as session:
        for config in configs:
            row = (await session.execute(select(Outlet).where(Outlet.slug == config.slug))).scalar_one_or_none()
            if row is None:
                row = Outlet(slug=config.slug, name=config.name, ip=config.ip)
                session.add(row)
            row.name = config.name
            row.ip = config.ip
            # Flush so a new row gets its id.
            await session.flush()
            infos.append(OutletInfo(id=row.id, slug=row.slug, name=row.name, ip=row.ip, model=config.model))
        await session.commit()
    return infos
