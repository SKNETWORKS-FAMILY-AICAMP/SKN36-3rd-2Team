"""Public NPC identities for case001_1120."""

from crimescene.chat.npc_persona import NPCPersona

NAMES = {
    "C01": "\uc724\ud0dc\uc2dd",
    "C02": "\ubb38\uc9c0\ud61c",
    "C03": "\ubc15\ub3c4\ud604",
    "C04": "\ucd5c\ubbfc\uc11d",
    "C05": "\uc815\uc720\ub77c",
    "C06": "\uc8fc\uccad",
    "C07": "\uc7a5\ud604\uc6b0",
    "C08": "\uc11c\ubbf8\ub780",
    "C09": "\ud6c4\uc9c0\uc774 \ub958",
    "C10": "\uc624\uc7ac\ubbfc",
}


def build_expanded_personas():
    return {
        npc_id: NPCPersona(
            character_id=npc_id,
            name=name,
            voice=(
                "Speak naturally in Korean. "
                "Use only verified character knowledge."
            ),
        )
        for npc_id, name in NAMES.items()
    }
