from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ServiceOption:
    slug: str
    service_selection_id: str
    name_en: str
    name_fi: str
    duration: str


@dataclass(frozen=True)
class CategoryOption:
    slug: str
    category_id: str
    name_en: str
    name_fi: str
    services: tuple[ServiceOption, ...]


SERVICE_CATEGORIES: tuple[CategoryOption, ...] = (
    CategoryOption(
        slug="citizenship",
        category_id="dafb977e-ba15-41b8-9aea-bb234abd8e31",
        name_en="Citizenship",
        name_fi="Kansalaisuusasia",
        services=(
            ServiceOption(
                slug="citizenship-matters",
                service_selection_id="000564ce-b800-4c2e-8040-62f50a09f55e",
                name_en="Citizenship matters",
                name_fi="Kansalaisuusasiat",
                duration="PT20M",
            ),
        ),
    ),
    CategoryOption(
        slug="eu-registration-brexit",
        category_id="5d9073ba-5a76-44b4-afd2-ba27032ba98c",
        name_en="EU registration / Brexit",
        name_fi="EU-rekisterointi / Brexit",
        services=(
            ServiceOption(
                slug="eu-citizen-registration",
                service_selection_id="e5e795f2-7f35-4b11-ba7d-d1c45cbec182",
                name_en="Registration of an EU citizen",
                name_fi="EU-kansalaisen rekisterointi",
                duration="PT30M",
            ),
            ServiceOption(
                slug="family-member-card",
                service_selection_id="a10919dc-4ada-461b-9041-beb9c603d99e",
                name_en="Card for a family member of an EU citizen",
                name_fi="EU-kansalaisen perheenjasenen kortti",
                duration="PT30M",
            ),
            ServiceOption(
                slug="brexit-appointments",
                service_selection_id="5ed69359-3e99-4756-8b05-0893b1a86ce6",
                name_en="Brexit appointments",
                name_fi="Brexit-ajat",
                duration="PT30M",
            ),
        ),
    ),
    CategoryOption(
        slug="residence-permit",
        category_id="1a50a292-62ed-4a46-831d-e724ac8cb35e",
        name_en="Residence permit",
        name_fi="Oleskelulupa",
        services=(
            ServiceOption(
                slug="work",
                service_selection_id="2906a690-4c8c-4276-bf2b-19b8cf2253f3",
                name_en="Work",
                name_fi="Tyo",
                duration="PT30M",
            ),
            ServiceOption(
                slug="family",
                service_selection_id="a87390ae-a870-44d4-80a7-ded974f4cb06",
                name_en="Family",
                name_fi="Perhe",
                duration="PT30M",
            ),
            ServiceOption(
                slug="study",
                service_selection_id="d9638dd8-fe83-47e6-8b59-dbfa414cfeb7",
                name_en="Study",
                name_fi="Opiskelu",
                duration="PT30M",
            ),
            ServiceOption(
                slug="other-grounds",
                service_selection_id="f2a99365-022e-44f8-8091-f96043eddc36",
                name_en="Other grounds",
                name_fi="Muu peruste",
                duration="PT30M",
            ),
            ServiceOption(
                slug="permanent-residence-permit",
                service_selection_id="3e03034d-a44b-4771-b1e5-2c4a6f581b7d",
                name_en="Permanent residence permit",
                name_fi="Pysyva oleskelulupa",
                duration="PT30M",
            ),
            ServiceOption(
                slug="renew-permanent-residence-permit-card",
                service_selection_id="f5daa984-ff85-427d-b2b0-546a7c3edf7b",
                name_en="Renewal of a permanent residence permit card",
                name_fi="Pysyvan oleskeluluvan kortin uusiminen",
                duration="PT20M",
            ),
            ServiceOption(
                slug="renew-residence-permit-card",
                service_selection_id="4f53e3ce-ad70-4a8b-ad87-5b505aa200c7",
                name_en="Renewal of residence permit card",
                name_fi="Oleskelulupakortin uusiminen",
                duration="PT30M",
            ),
        ),
    ),
    CategoryOption(
        slug="temporary-protection",
        category_id="73089c47-a3ed-4a4a-b342-924f38c8950c",
        name_en="Temporary protection",
        name_fi="Tilapainen suojelu",
        services=(
            ServiceOption(
                slug="temporary-protection-residence-permit-card",
                service_selection_id="fb27b72c-1976-4ad4-a5fe-daf37af67fb1",
                name_en="Temporary protection residence permit card",
                name_fi="Tilapainen suojelu: Oleskelulupakortin hakeminen",
                duration="PT30M",
            ),
        ),
    ),
    CategoryOption(
        slug="travel-document",
        category_id="1a88df32-3da8-4d91-a339-9ce1f1ec4cf8",
        name_en="Travel document",
        name_fi="Matkustusasiakirja",
        services=(
            ServiceOption(
                slug="aliens-passport",
                service_selection_id="28af9eb7-64f7-4e78-aaf4-3242909490c4",
                name_en="Alien's passport",
                name_fi="Muukalaispassi",
                duration="PT30M",
            ),
            ServiceOption(
                slug="refugee-travel-document",
                service_selection_id="b8daed03-9b93-426d-a2eb-87e2da3bed64",
                name_en="Refugee travel document",
                name_fi="Pakolaisen matkustusasiakirja",
                duration="PT30M",
            ),
        ),
    ),
)

CATEGORIES_BY_SLUG = {category.slug: category for category in SERVICE_CATEGORIES}
