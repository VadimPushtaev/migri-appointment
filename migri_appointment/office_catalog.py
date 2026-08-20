from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class OfficeOption:
    slug: str
    office_id: str
    display_name: str
    aliases: tuple[str, ...] = ()


OFFICES: tuple[OfficeOption, ...] = (
    OfficeOption(
        slug="helsinki",
        office_id="438cd01e-9d81-40d9-b31d-5681c11bd974",
        display_name="Helsinki",
    ),
    OfficeOption(
        slug="turku",
        office_id="074cc6f8-735b-4ea5-ad9a-9e517fef09bb",
        display_name="Turku (Raisio)",
        aliases=("raisio",),
    ),
    OfficeOption(
        slug="tampere",
        office_id="08d44a6b-af37-4a30-8462-1d6f5fc5cd61",
        display_name="Tampere",
    ),
    OfficeOption(
        slug="oulu",
        office_id="a4657f2f-eacd-4668-9c2b-92a7cdd44408",
        display_name="Oulu",
    ),
    OfficeOption(
        slug="lahti",
        office_id="a893849c-c0d9-489b-92a3-6dd8a36ef9f9",
        display_name="Lahti",
    ),
    OfficeOption(
        slug="kuopio",
        office_id="10a1fb12-3783-4a3b-a532-468b93bb85c9",
        display_name="Kuopio",
    ),
    OfficeOption(
        slug="lappeenranta",
        office_id="b84cfd93-4cf9-40e7-ad79-78aca8c422a0",
        display_name="Lappeenranta",
    ),
    OfficeOption(
        slug="vaasa",
        office_id="6b5d9667-e526-4136-af5a-b1d20f5d01b3",
        display_name="Vaasa",
    ),
    OfficeOption(
        slug="rovaniemi",
        office_id="891474c3-f7ee-4fe8-a542-38169726503a",
        display_name="Rovaniemi",
    ),
    OfficeOption(
        slug="aland",
        office_id="87558cb4-975b-46e9-a411-51ca67c56a08",
        display_name="Åland (Mariehamn)",
        aliases=("åland", "ahvenanmaa", "ahvenanmaa-aland", "mariehamn"),
    ),
)

DEFAULT_CITY_SLUG = "helsinki"
OFFICES_BY_CITY_SLUG = {
    city_slug: office
    for office in OFFICES
    for city_slug in (office.slug, *office.aliases)
}
CITY_SLUGS = tuple(sorted(OFFICES_BY_CITY_SLUG))


def normalize_city_slug(value: str) -> str:
    return value.strip().casefold()
