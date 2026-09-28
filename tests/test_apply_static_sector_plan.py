import importlib.util
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "apply_static_sector_plan.py"
SPEC = importlib.util.spec_from_file_location("apply_static_sector_plan", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class ApplyStaticSectorPlanTests(unittest.TestCase):
    def rows(self):
        return [
            MODULE.PlanRow("Central Black Hole", "Root", "RealGasGiant", "Giant-1", "", "0", "0", "0", "0", "0", "0", "0"),
            MODULE.PlanRow("Star", "Star A", "RealStar", "Star-1", "Root", "1000", "0.1", "1", "2", "3", "40", "0.5"),
            MODULE.PlanRow("Planet", "World", "Tellus", "Tellus-1", "Star A", "2000", "0", "0", "0", "0", "50", "1"),
        ]

    @staticmethod
    def body(storage, name, planet_type):
        node = ET.Element("RootBody", {"BodyInstanceName": storage})
        ET.SubElement(node, "Name").text = name
        ET.SubElement(node, "PlanetTypeId").text = planet_type
        ET.SubElement(node, "PlanetOrbitZoneRadius").text = "123"
        ET.SubElement(node, "ParticleInfoConfig")
        ET.SubElement(node, "FunctionalZoneInfoConfig")
        ET.SubElement(node, "SpecialInfoConfig")
        ET.SubElement(node, "Children")
        return node

    def rss_root(self, suffix=""):
        root = ET.Element("RealSolarSystemsSettingsConfig")
        ET.SubElement(root, "OverrideFromConfig").text = "false"
        systems = ET.SubElement(root, "SolarSystems")
        for storage, name, planet_type in (("Giant-1", "Old G", "RealGasGiant"), ("Star-1", "Old S", "RealStar"), ("Tellus-1", "Old P", "Tellus")):
            system = ET.SubElement(systems, "SolarSystemConfig")
            ET.SubElement(system, "Position")
            system.append(self.body(storage + suffix, name, planet_type))
        return root

    def test_rebuilds_hierarchy_and_preserves_body_specific_fields(self):
        root = self.rss_root()
        indexed, _ = MODULE.update_rss(root, self.rows())
        systems = root.find("SolarSystems")
        self.assertEqual(1, len(systems.findall("SolarSystemConfig")))
        black_hole = systems.find("./SolarSystemConfig/RootBody")
        self.assertEqual("Root", black_hole.findtext("Name"))
        star = black_hole.find("./Children/CelestialBodyConfig")
        self.assertEqual("Star A", star.findtext("Name"))
        planet = star.find("./Children/CelestialBodyConfig")
        self.assertEqual("World", planet.findtext("Name"))
        self.assertEqual("2000", planet.findtext("./OrbitInfo/SemimajorAxis"))
        self.assertEqual("123", planet.findtext("PlanetOrbitZoneRadius"))
        self.assertEqual("true", root.findtext("OverrideFromConfig"))
        self.assertEqual("Star-1", indexed["Star-1"][0])

    def test_unique_numeric_suffix_is_accepted(self):
        root = self.rss_root(".01")
        indexed, _ = MODULE.update_rss(root, self.rows())
        self.assertEqual("Tellus-1.01", indexed["Tellus-1"][0])

    def test_exact_match_wins_over_suffix(self):
        self.assertEqual("Body", MODULE.unique_identity_match("Body", ["Body.01", "Body"], "test"))

    def test_ambiguous_numeric_suffix_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "numeric-suffix"):
            MODULE.unique_identity_match("Body", ["Body.01", "Body.02"], "test")

    def test_unplanned_rss_body_is_rejected(self):
        root = self.rss_root()
        systems = root.find("SolarSystems")
        extra = ET.SubElement(systems, "SolarSystemConfig")
        extra.append(self.body("Extra-1", "Extra", "Moon"))
        with self.assertRaisesRegex(RuntimeError, "RSS saved 4 bodies"):
            MODULE.update_rss(root, self.rows())

    def test_updates_sector_names_without_changing_identity(self):
        root = ET.Element("Sector")
        for row in self.rows():
            body = ET.SubElement(root, "MyObjectBuilder_Planet")
            ET.SubElement(body, "Name").text = "Old"
            ET.SubElement(body, "StorageName").text = row.storage_name
            ET.SubElement(body, "PlanetGenerator").text = row.planet_type
        indexed = MODULE.update_sector(root, self.rows())
        self.assertEqual("World", indexed["Tellus-1"][1].findtext("Name"))
        self.assertEqual("Tellus-1", indexed["Tellus-1"][1].findtext("StorageName"))

    def test_updates_external_custom_name_and_override(self):
        root = ET.Element("RealSunConfig")
        ET.SubElement(root, "OverrideFromConfig").text = "false"
        star = ET.SubElement(root, "StarInfo", {"StarName": "Star-1"})
        ET.SubElement(star, "StarCustomName").text = "Old S"
        MODULE.update_named_config(root, self.rows(), "StarInfo", "StarName", "StarCustomName", {"RealStar"}, "Real Stars")
        self.assertEqual("Star A", star.findtext("StarCustomName"))
        self.assertEqual("true", root.findtext("OverrideFromConfig"))

    def test_plan_requires_known_parent(self):
        text = "Role\tName\tPlanetType\tStorageName\tParent\tSemimajorAxisM\tEccentricity\tPitch\tRoll\tYaw\tOrbitalPeriodS\tOrbitalPeriodOffset\nRoot\tA\tRealStar\tA-1\t\t0\t0\t0\t0\t0\t0\t0\nPlanet\tB\tTellus\tB-1\tMissing\t1\t0\t0\t0\t0\t1\t0\n"
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "plan.tsv"
            path.write_text(text, encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "Unknown parent"):
                MODULE.load_plan(path)


if __name__ == "__main__":
    unittest.main()
