using Sandbox.Definitions;
using Sandbox.Game.Entities;
using Sandbox.ModAPI;
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using VRage.Game.Components;
using VRage.Game.ModAPI;
using VRage.ModAPI;
using VRage.Utils;
using VRage.Voxels;
using VRageMath;

namespace RandomSectorGenerator
{
    [MySessionComponentDescriptor(MyUpdateOrder.AfterSimulation)]
    public sealed class RandomSectorGeneratorSession : MySessionComponentBase
    {
        private const string Author = "Random Sector Generator";
        private const string Version = "0.2.0-audit";
        private const string CommandPrefix = "/rsg";
        private const string StateFileName = "RandomSectorGenerator.State.xml";
        private const string ManifestFileName = "RandomSectorGenerator.Manifest.txt";
        private const string ArmKey = "RSG_DisposableBootstrap_v1";
        private static readonly HashSet<string> AllowedPlanets = new HashSet<string>(StringComparer.Ordinal)
        {
            "Cauldron", "Tellus", "Agni", "Kor", "Teal-WaterMod", "Teralis - City Planet", "Zenitaia",
            "EarthLike", "Moon", "Mars", "Europa"
        };
        private static readonly HashSet<ulong> DeniedWorkshopIds = new HashSet<ulong>
        {
            2873186053UL, 2266665708UL, 2636128625UL, 2296726670UL, 2459246911UL,
            3617008256UL, 3617040986UL, 3618093811UL, 3617496051UL, 3561998389UL,
            2603627657UL, 2789619117UL
        };

        private const int MaximumPlanetDefinitions = 24;
        private const double SystemSpacingMin = 6000000000d;   // 6 million km
        private const double SystemSpacingMax = 12000000000d;  // 12 million km
        private const double TrueSpaceMinRadius = 650000000d;  // RSS true-space parking area
        private const double TrueSpaceMaxRadius = 1125000000d;
        private const double TrueSpaceMinSeparation = 30000000d;

        private readonly RealStarsClient _realStars = new RealStarsClient();
        private readonly RealGasGiantsClient _realGasGiants = new RealGasGiantsClient();
        private readonly RealSolarSystemsClient _rss = new RealSolarSystemsClient();
        private readonly List<Vector3D> _usedTrueSpacePositions = new List<Vector3D>();

        private PendingSectorState _state = new PendingSectorState();
        private bool _chatRegistered;
        private bool _pendingAdoptionCheck;
        private int _ticks;
        private bool _adoptionNoticeShown;
        private bool _startTeleportDone;
        private bool _autoAttempted;

        public override void LoadData()
        {
            _state = ReadState();

            // The offline handoff writes the pending payload to the checkpoint AFTER
            // the first save and game exit. RSS then reads it normally on next load.
            // Session component priority does not order LoadData in this game build.
            if (_state != null && _state.PendingApply && !string.IsNullOrWhiteSpace(_state.RssConfigBase64))
            {
                _pendingAdoptionCheck = true;
                MyLog.Default.WriteLineAndConsole("[RSG] Checking pending sector adoption; offline handoff must precede reload.");
            }

            _realStars.Load();
            _realGasGiants.Load();
            _rss.Load();
        }

        public override void UpdateAfterSimulation()
        {
            _ticks++;

            if (!_chatRegistered && MyAPIGateway.Utilities != null && MyAPIGateway.Session != null && MyAPIGateway.Session.Player != null)
            {
                MyAPIGateway.Utilities.MessageEntered += OnMessageEntered;
                _chatRegistered = true;
            }

            if (_ticks % 180 == 0)
            {
                if (!_realStars.IsReady && !_realStars.Compromised) _realStars.Load();
                if (!_realGasGiants.IsReady && !_realGasGiants.Compromised) _realGasGiants.Load();
                if (!_rss.IsReady && !_rss.Compromised) _rss.Load();
            }

            if (_pendingAdoptionCheck && _state != null && _state.PendingApply)
                CheckRssAdoptionAndFinishBootstrap();

            string armed;
            if (!_autoAttempted && IsServer() && _ticks >= 600 && _realStars.IsReady && _realGasGiants.IsReady && _rss.IsReady &&
                !_state.PendingApply && !_state.Applied && !_state.InProgress && !_state.Failed &&
                MyAPIGateway.Utilities.GetVariable(ArmKey, out armed) && armed == "armed")
            {
                _autoAttempted = true;
                GenerateSector(unchecked((int)DateTime.UtcNow.Ticks));
            }
        }

        protected override void UnloadData()
        {
            if (_chatRegistered && MyAPIGateway.Utilities != null)
                MyAPIGateway.Utilities.MessageEntered -= OnMessageEntered;

            _realStars.Unload();
            _realGasGiants.Unload();
            _rss.Unload();
            _usedTrueSpacePositions.Clear();
            _chatRegistered = false;
        }

        private void OnMessageEntered(string messageText, ref bool sendToOthers)
        {
            if (string.IsNullOrWhiteSpace(messageText) || !messageText.StartsWith(CommandPrefix, StringComparison.OrdinalIgnoreCase))
                return;

            sendToOthers = false;
            string[] tokens = messageText.Trim().Split(new[] { ' ' }, StringSplitOptions.RemoveEmptyEntries);
            string command = tokens.Length > 1 ? tokens[1].ToLowerInvariant() : "help";

            if (command == "help")
            {
                Show("Commands: /rsg status | /rsg skins | /rsg planets | /rsg generate [seed]");
                return;
            }

            if (command == "status")
            {
                ShowStatus();
                return;
            }

            if (command == "skins")
            {
                ShowSkins();
                return;
            }

            if (command == "planets")
            {
                ShowPlanetDefinitions();
                return;
            }

            if (command == "generate")
            {
                int seed;
                if (tokens.Length > 2 && int.TryParse(tokens[2], out seed))
                {
                    GenerateSector(seed);
                }
                else if (tokens.Length <= 2)
                {
                    GenerateSector(unchecked((int)DateTime.UtcNow.Ticks));
                }
                else Show("Seed must be a signed 32-bit integer.");
                return;
            }

            Show("Unknown command. Use /rsg help");
        }

        private void ShowStatus()
        {
            StringBuilder sb = new StringBuilder();
            sb.Append("v").Append(Version).Append(" | ");
            sb.Append("Real Stars=").Append(_realStars.IsReady ? "ready" : "not ready");
            sb.Append(" | Real Gas Giants=").Append(_realGasGiants.IsReady ? "ready" : "not ready");
            sb.Append(" | RSS=").Append(_rss.IsReady ? "ready" : "not ready");

            if (_state != null && (_state.PendingApply || _state.Applied))
            {
                sb.Append(" | seed=").Append(_state.Seed);
                sb.Append(" | systems=").Append(_state.StellarSystemCount);
                sb.Append(" | planets=").Append(_state.PlanetDefinitionCount);
                sb.Append(" | pending=").Append(_state.PendingApply);
                sb.Append(" | applied=").Append(_state.Applied);
            }

            Show(sb.ToString());
        }

        private void ShowSkins()
        {
            if (!_realGasGiants.IsReady)
            {
                Show("Real Gas Giants API is not ready yet. Wait a moment and try again.");
                return;
            }

            List<string> skins = _realGasGiants.GetSkins();
            string blackHole = SelectBlackHoleSkin(skins);
            Show("Gas giant skins: " + (skins.Count == 0 ? "<none>" : string.Join(", ", skins)));
            Show("Black-hole candidate: " + (blackHole ?? "<none found>"));
        }

        private void ShowPlanetDefinitions()
        {
            List<MyPlanetGeneratorDefinition> defs = GetUsablePlanetDefinitions();
            Show("Enabled usable planet definitions (" + defs.Count + "): " + string.Join(", ", defs.Select(x => x.Id.SubtypeId.ToString())));
        }

        private void GenerateSector(int seed)
        {
            if (!IsServer())
            {
                Show("Generation must be run by the server/host.");
                return;
            }

            string armed;
            if (!MyAPIGateway.Utilities.GetVariable(ArmKey, out armed) || armed != "armed")
            {
                Show("Generation refused: only an offline-prepared disposable bootstrap world may generate.");
                return;
            }
            if (_state.Applied || _state.InProgress || _state.Failed)
            {
                Show("Generation locked: completed or interrupted bootstrap. Restore the disposable baseline; do not retry in this save.");
                return;
            }
            foreach (var mod in MyAPIGateway.Session.Mods)
            {
                if (DeniedWorkshopIds.Contains(mod.PublishedFileId))
                {
                    Show("Generation refused: a denylisted Workshop mod is active: " + mod.PublishedFileId);
                    return;
                }
            }
            int materialCount = MyDefinitionManager.Static.GetVoxelMaterialDefinitions().Select(x => x.Id.SubtypeName).Distinct().Count();
            if (materialCount > 120)
            {
                Show("Generation refused: loaded voxel material count " + materialCount + " exceeds the safety budget of 120.");
                return;
            }

            if (_state != null && _state.PendingApply)
            {
                Show("A generated sector is already waiting to be applied. Save, quit to menu, and reload this world first.");
                return;
            }

            if (!_realStars.IsReady || !_realGasGiants.IsReady)
            {
                _realStars.Load();
                _realGasGiants.Load();
                Show("Real Stars / Real Gas Giants APIs are not ready yet. Wait a few seconds, run /rsg status, then retry.");
                return;
            }

            List<MyPlanet> existingPlanets = GetLoadedPlanets();
            if (existingPlanets.Count > 0)
            {
                Show("Generation refused: this world already contains " + existingPlanets.Count + " planet/star entities. Use the RSS Empty World template for the first generation.");
                return;
            }

            List<MyPlanetGeneratorDefinition> definitions = GetUsablePlanetDefinitions();
            if (definitions.Count < 4)
            {
                Show("Not enough usable planet definitions are enabled. Found " + definitions.Count + ".");
                return;
            }

            Random rng = new Random(seed);
            Shuffle(definitions, rng);
            if (definitions.Count > MaximumPlanetDefinitions)
                definitions = definitions.Take(MaximumPlanetDefinitions).ToList();

            MyPlanetGeneratorDefinition starterDefinition = ChooseStarterDefinition(definitions);
            if (starterDefinition == null)
            {
                Show("Generation refused: no approved starter (Tellus or EarthLike) is available.");
                return;
            }
            definitions.Remove(starterDefinition);
            definitions.Insert(0, starterDefinition);

            List<string> skins = _realGasGiants.GetSkins();
            string blackHoleSkin = SelectBlackHoleSkin(skins);
            List<string> normalGasSkins = skins.Where(x => !string.Equals(x, blackHoleSkin, StringComparison.OrdinalIgnoreCase)).ToList();

            if (blackHoleSkin == null)
            {
                Show("Generation refused: the verified DefaultBlackHole skin is unavailable.");
                return;
            }

            RssSettingsWire config = new RssSettingsWire();
            SectorBuildContext build = new SectorBuildContext(rng, config);
            _usedTrueSpacePositions.Clear();

            try
            {
                _state = new PendingSectorState { InProgress = true, Seed = seed };
                WriteState(_state); // Durable lock before the first entity is spawned.
                BuildSector(build, definitions, starterDefinition, normalGasSkins, blackHoleSkin);
                if (blackHoleSkin != null && build.BlackHole == null)
                    throw new Exception("Required black hole failed to spawn.");
                ValidateSector(config);

            if (build.StartPlanet == null)
                throw new Exception("Starter planet did not spawn.");

            byte[] bytes = MyAPIGateway.Utilities.SerializeToBinary(config);
            string encoded = Convert.ToBase64String(bytes);

            _state = new PendingSectorState
            {
                PendingApply = true,
                Applied = false,
                Seed = seed,
                StellarSystemCount = build.Config.SolarSystems.Count,
                PlanetDefinitionCount = definitions.Count,
                GeneratedGasGiants = build.GasGiantCount,
                GeneratedBlackHole = build.BlackHole != null,
                BlackHoleSkin = blackHoleSkin,
                StartPlanetDisplayName = build.StartPlanet.Name,
                StartPlanetSubtype = starterDefinition.Id.SubtypeId.ToString(),
                StartPlanetEntityId = build.StartPlanet.EntityId,
                RssConfigBase64 = encoded,
                CreatedUtc = DateTime.UtcNow.ToString("o")
            };
            _state.GeneratedEntityIds = build.GeneratedEntities.Select(x => x.EntityId).ToList();

            WriteState(_state);
            WriteManifest(build, definitions, seed, blackHoleSkin);

            TeleportCharacterToUnmanagedStarter(build.StartPlanet);

            Show("Random sector generated. Seed " + seed + ".");
            Show("Starter: " + build.StartPlanet.Name + " (" + starterDefinition.Id.SubtypeId + "). The rest of the sector layout is intentionally hidden.");
            Show("SAVE, then EXIT THE GAME. The local handoff tool will commit the pending RSS config before reload. Do not start survival yet.");
            }
            catch (Exception e)
            {
                MyLog.Default.WriteLineAndConsole("[RSG] Sector generation failed: " + e);
                RollbackGeneratedEntities(build);
                _state = new PendingSectorState { Failed = true, Seed = seed };
                try { WriteState(_state); } catch { }
                Show("Generation failed and this bootstrap is locked. Restore the disposable baseline before retrying; inspect SpaceEngineers.log.");
            }
        }

        private void BuildSector(SectorBuildContext build, List<MyPlanetGeneratorDefinition> definitions, MyPlanetGeneratorDefinition starterDefinition, List<string> normalGasSkins, string blackHoleSkin)
        {
            // Five physical stars gives us four logical root systems when two stars
            // are grouped under the guaranteed black-hole cluster. Without a known
            // black-hole skin, generate four independent stellar systems.
            int rootCount = build.Random.Next(3, 6);
            int stellarSystemCount = string.IsNullOrWhiteSpace(blackHoleSkin) ? rootCount : rootCount + 1;

            // Spawn the physical Real Stars first. RSS will find them by StorageName after reload.
            for (int i = 0; i < stellarSystemCount; i++)
            {
                string starName = GenerateUniqueName(build) + " Star";
                Vector3D truePos = NextTrueSpacePosition(build.Random);
                Vector3I color = RandomStarColor(build.Random);
                float radiusKm = 45f + (float)build.Random.NextDouble() * 35f;
                float brightness = 0.8f + (float)build.Random.NextDouble() * 0.8f;

                MyPlanet star = _realStars.SpawnStar(truePos, radiusKm, color, brightness, brightness, radiusKm * 3f, 10f, 7f);
                if (star == null)
                    throw new Exception("Real Stars SpawnStar returned null for system " + i);

                star.Name = starName;
                _realStars.SetStarName(star, starName);
                build.GeneratedEntities.Add(star);

                RssBodyWire starBody = CreateSpecialBody("RealStar", starName, star.StorageName, Math.Max(radiusKm * 5000f, 500000f));
                build.Stars.Add(new StarBuildNode { Entity = star, Body = starBody, Name = starName });
            }

            // Home system always remains a normal independent star at logical origin.
            build.Config.SolarSystems.Add(new RssSolarSystemWire
            {
                Position = Vector3D.Zero,
                RootBody = build.Stars[0].Body
            });

            // Guarantee one black-hole cluster when a recognized RGG skin exists.
            int clusterStart = Math.Max(2, build.Stars.Count - 2);
            HashSet<int> clusteredStarIndices = new HashSet<int>();
            if (!string.IsNullOrWhiteSpace(blackHoleSkin) && build.Stars.Count >= 4)
            {
                string holeName = GenerateUniqueName(build) + " Abyss";
                Vector3D holeTruePos = NextTrueSpacePosition(build.Random);
                MyPlanet hole = _realGasGiants.SpawnGasGiant(holeTruePos, 180f, new Vector3I(8, 8, 12), blackHoleSkin, 35f, 2f, 3600f);
                if (hole != null)
                {
                    hole.Name = holeName;
                    _realGasGiants.SetGasGiantName(hole, holeName);
                    build.GeneratedEntities.Add(hole);
                    RssBodyWire holeBody = CreateSpecialBody("RealGasGiant", holeName, hole.StorageName, 900000f);
                    build.BlackHole = hole;
                    build.BlackHoleBody = holeBody;
                    build.GasGiantCount++;

                    float orbit = 1400000000f;
                    for (int i = clusterStart; i < build.Stars.Count; i++)
                    {
                        RssBodyWire starBody = build.Stars[i].Body;
                        AttachChild(holeBody, starBody, orbit, build.Random, 0.04f);
                        orbit += 900000000f;
                        clusteredStarIndices.Add(i);
                    }

                    build.Config.SolarSystems.Add(new RssSolarSystemWire
                    {
                        Position = RandomSystemPosition(build.Random, build.Config.SolarSystems.Select(x => x.Position).ToList()),
                        RootBody = holeBody
                    });
                }
            }

            // Independent non-home systems that were not folded into the black-hole cluster.
            for (int i = 1; i < build.Stars.Count; i++)
            {
                if (clusteredStarIndices.Contains(i))
                    continue;

                build.Config.SolarSystems.Add(new RssSolarSystemWire
                {
                    Position = RandomSystemPosition(build.Random, build.Config.SolarSystems.Select(x => x.Position).ToList()),
                    RootBody = build.Stars[i].Body
                });
            }

            // Add up to two normal gas giants, giving some custom planets a chance to become moons.
            int gasGiantTarget = normalGasSkins.Count > 0 ? Math.Min(2, build.Stars.Count) : 0;
            for (int i = 0; i < gasGiantTarget; i++)
            {
                int starIndex = (i + 1) % build.Stars.Count; // don't force the starter world's first major body to be a gas giant
                string skin = normalGasSkins[build.Random.Next(normalGasSkins.Count)];
                string name = GenerateUniqueName(build) + " Giant";
                Vector3D truePos = NextTrueSpacePosition(build.Random);
                Vector3I color = new Vector3I(build.Random.Next(50, 240), build.Random.Next(50, 240), build.Random.Next(50, 240));

                float giantRadiusKm = 90f + (float)build.Random.NextDouble() * 70f;
                MyPlanet giant = _realGasGiants.SpawnGasGiant(truePos, giantRadiusKm, color, skin, 4f, 3f, 7200f + build.Random.Next(0, 7200));
                if (giant == null)
                    continue;

                giant.Name = name;
                _realGasGiants.SetGasGiantName(giant, name);
                build.GeneratedEntities.Add(giant);
                RssBodyWire giantBody = CreateSpecialBody("RealGasGiant", name, giant.StorageName, Math.Max(giantRadiusKm * 5000f, 500000f));
                AttachChild(build.Stars[starIndex].Body, giantBody, NextStarOrbit(build.Stars[starIndex]), build.Random, 0.06f);
                build.Stars[starIndex].GasGiantBody = giantBody;
                build.GasGiantCount++;
            }

            // Assign every enabled planet definition. The first one is the selected starter.
            for (int i = 0; i < definitions.Count; i++)
            {
                MyPlanetGeneratorDefinition def = definitions[i];
                bool isStarter = def == starterDefinition;

                int starIndex;
                if (isStarter)
                {
                    starIndex = 0;
                }
                else if (i <= build.Stars.Count)
                {
                    starIndex = (i - 1) % build.Stars.Count;
                }
                else
                {
                    starIndex = build.Random.Next(build.Stars.Count);
                }

                StarBuildNode starNode = build.Stars[starIndex];
                bool useGasGiantMoon = !isStarter && starNode.GasGiantBody != null && build.Random.NextDouble() < 0.28;
                bool usePlanetMoon = !isStarter && !useGasGiantMoon && starNode.LastDirectPlanet != null && build.Random.NextDouble() < 0.15;
                bool moon = useGasGiantMoon || usePlanetMoon;

                int diameterKm = moon ? build.Random.Next(19, 41) : build.Random.Next(60, 121);
                float radiusMeters = diameterKm * 500f;
                string displayName = GenerateUniqueName(build);
                RssBodyWire body = CreateTerrestrialBody(def.Id.SubtypeId.ToString(), displayName, radiusMeters, build.Random);

                if (isStarter)
                {
                    MyPlanet startPlanet = SpawnStarterPlanet(def, body, radiusMeters, build.Random);
                    if (startPlanet == null)
                        throw new Exception("SpawnPlanet returned null for starter definition " + def.Id.SubtypeId);
                    build.StartPlanet = startPlanet;
                    build.GeneratedEntities.Add(startPlanet);
                }

                if (useGasGiantMoon)
                {
                    AttachChild(starNode.GasGiantBody, body, NextMoonOrbit(starNode.GasGiantBody, build.Random), build.Random, 0.03f);
                }
                else if (usePlanetMoon)
                {
                    AttachChild(starNode.LastDirectPlanet, body, NextMoonOrbit(starNode.LastDirectPlanet, build.Random), build.Random, 0.02f);
                }
                else
                {
                    AttachChild(starNode.Body, body, NextStarOrbit(starNode), build.Random, 0.08f);
                    starNode.LastDirectPlanet = body;
                }

                build.PlanetSubtypeByName[displayName] = def.Id.SubtypeId.ToString();
            }
        }

        private MyPlanet SpawnStarterPlanet(MyPlanetGeneratorDefinition def, RssBodyWire body, float radiusMeters, Random rng)
        {
            Vector3D center = NextTrueSpacePosition(rng);
            float diameterMeters = radiusMeters * 2f;
            Vector3D spawnPosition = CalculatePlanetSpawnPosition(def, diameterMeters, center);
            int seed = rng.Next(1, int.MaxValue);

            IMyVoxelBase voxel = MyAPIGateway.Session.VoxelMaps.SpawnPlanet(def.Id.SubtypeId.ToString(), diameterMeters, seed, spawnPosition);
            MyPlanet planet = voxel as MyPlanet;
            if (planet == null)
                return null;

            planet.Name = body.Name;
            body.BodyInstanceName = planet.StorageName;
            return planet;
        }

        private static Vector3D CalculatePlanetSpawnPosition(MyPlanetGeneratorDefinition def, float diameterMeters, Vector3D desiredCenter)
        {
            float radius = diameterMeters * 0.5f;
            float boundingRadius = radius * (1f + def.HillParams.Max);
            Vector3I boundingSize = MyVoxelCoordSystems.FindBestOctreeSize(2f * boundingRadius);
            Vector3D offset = (Vector3D)boundingSize * 0.5d;
            return desiredCenter - offset;
        }

        private RssBodyWire CreateTerrestrialBody(string subtype, string name, float radiusMeters, Random rng)
        {
            RssBodyWire body = new RssBodyWire();
            body.BodyInstanceName = "None"; // RSS requires a non-null string during its legacy-name migration step.
            body.Name = name;
            body.PlanetTypeId = subtype;
            body.PlanetProxyScale = 1f;
            body.AsteroidsEnabled = true;
            body.PlanetOrbitZoneRadius = Math.Max(radiusMeters * 5f, 500000f);
            body.TerrestrialPlanetInfo = new RssTerrestrialWire
            {
                RadiusKm = radiusMeters * 0.001f,
                PlanetSurfaceZoneRadius = radiusMeters,
                PlanetProxyFadeoutHeightMult = 0f,
                PlanetRotationPeriod = rng.Next(3600, 18001),
                PlanetRotationPeriodOffset = (float)(rng.NextDouble() * Math.PI * 2d),
                GravityStrength = -1f,
                GravityFalloff = -1f
            };
            return body;
        }

        private static RssBodyWire CreateSpecialBody(string subtype, string name, string storageName, float orbitZoneRadius)
        {
            return new RssBodyWire
            {
                BodyInstanceName = storageName,
                Name = name,
                PlanetTypeId = subtype,
                PlanetOrbitZoneRadius = orbitZoneRadius,
                PlanetProxyScale = 1f,
                AsteroidsEnabled = true
            };
        }

        private static void AttachChild(RssBodyWire parent, RssBodyWire child, float semimajorAxis, Random rng, float maxEccentricity)
        {
            child.OrbitInfo = new RssOrbitWire
            {
                SemimajorAxis = semimajorAxis,
                Eccentricity = (float)(rng.NextDouble() * maxEccentricity),
                Pitch = (float)(rng.NextDouble() * 8d - 4d),
                Roll = (float)(rng.NextDouble() * 8d - 4d),
                Yaw = (float)(rng.NextDouble() * 360d),
                OrbitalPeriod = Math.Max(3600f, semimajorAxis / 400f),
                OrbitalPeriodOffset = (float)(rng.NextDouble() * Math.PI * 2d)
            };
            parent.Children.Add(child);
            parent.PlanetOrbitZoneRadius = Math.Max(parent.PlanetOrbitZoneRadius, semimajorAxis * 1.20f);
        }

        private static float NextStarOrbit(StarBuildNode star)
        {
            int index = star.Body.Children.Count + 1;
            return 25000000f + index * 28000000f;
        }

        private static float NextMoonOrbit(RssBodyWire parent, Random rng)
        {
            int index = parent.Children.Count + 1;
            return 1200000f + index * 1600000f + rng.Next(0, 800000);
        }

        private Vector3D NextTrueSpacePosition(Random rng)
        {
            for (int attempt = 0; attempt < 200; attempt++)
            {
                Vector3D dir = RandomUnitVector(rng);
                double radius = TrueSpaceMinRadius + rng.NextDouble() * (TrueSpaceMaxRadius - TrueSpaceMinRadius);
                Vector3D candidate = dir * radius;
                bool clear = true;
                for (int i = 0; i < _usedTrueSpacePositions.Count; i++)
                {
                    if (Vector3D.DistanceSquared(candidate, _usedTrueSpacePositions[i]) < TrueSpaceMinSeparation * TrueSpaceMinSeparation)
                    {
                        clear = false;
                        break;
                    }
                }

                if (clear)
                {
                    _usedTrueSpacePositions.Add(candidate);
                    return candidate;
                }
            }

            throw new Exception("Unable to find a separated physical position.");
        }

        private static Vector3D RandomSystemPosition(Random rng, List<Vector3D> existing)
        {
            for (int attempt = 0; attempt < 100; attempt++)
            {
                Vector3D candidate = RandomUnitVector(rng) * (SystemSpacingMin + rng.NextDouble() * (SystemSpacingMax - SystemSpacingMin));
                bool clear = true;
                for (int i = 0; i < existing.Count; i++)
                {
                    if (Vector3D.DistanceSquared(candidate, existing[i]) < SystemSpacingMin * SystemSpacingMin)
                    {
                        clear = false;
                        break;
                    }
                }
                if (clear)
                    return candidate;
            }
            throw new Exception("Unable to find a separated system position.");
        }

        private static Vector3D RandomUnitVector(Random rng)
        {
            double z = rng.NextDouble() * 2d - 1d;
            double theta = rng.NextDouble() * Math.PI * 2d;
            double planar = Math.Sqrt(Math.Max(0d, 1d - z * z));
            return new Vector3D(planar * Math.Cos(theta), z, planar * Math.Sin(theta));
        }

        private static Vector3I RandomStarColor(Random rng)
        {
            Vector3I[] palette =
            {
                new Vector3I(255, 244, 220),
                new Vector3I(255, 215, 170),
                new Vector3I(255, 180, 110),
                new Vector3I(210, 225, 255),
                new Vector3I(165, 195, 255),
                new Vector3I(255, 115, 80)
            };
            return palette[rng.Next(palette.Length)];
        }

        private static string SelectBlackHoleSkin(List<string> skins)
        {
            if (skins == null)
                return null;

            string[] preferred = { "DefaultBlackHole" };
            for (int p = 0; p < preferred.Length; p++)
            {
                string exact = skins.FirstOrDefault(x => string.Equals(x, preferred[p], StringComparison.OrdinalIgnoreCase));
                if (exact != null)
                    return exact;
            }

            return null; // Only locally verified black-hole skins are eligible.
        }

        private static MyPlanetGeneratorDefinition ChooseStarterDefinition(List<MyPlanetGeneratorDefinition> defs)
        {
            string[] preferred = { "Tellus", "EarthLike" };
            for (int i = 0; i < preferred.Length; i++)
            {
                MyPlanetGeneratorDefinition match = defs.FirstOrDefault(d => string.Equals(d.Id.SubtypeId.ToString(), preferred[i], StringComparison.Ordinal));
                if (match != null)
                    return match;
            }

            return null;
        }

        private static List<MyPlanetGeneratorDefinition> GetUsablePlanetDefinitions()
        {
            List<MyPlanetGeneratorDefinition> result = MyDefinitionManager.Static.GetPlanetsGeneratorsDefinitions().Where(IsUsablePlanetDefinition).ToList();
            result.Sort((a, b) => string.Compare(a.Id.SubtypeId.ToString(), b.Id.SubtypeId.ToString(), StringComparison.OrdinalIgnoreCase));
            return result;
        }

        private static bool IsUsablePlanetDefinition(MyPlanetGeneratorDefinition def)
        {
            if (def == null)
                return false;

            string name = def.Id.SubtypeId.ToString();
            if (string.IsNullOrWhiteSpace(name))
                return false;

            if (string.Equals(name, "RealStar", StringComparison.OrdinalIgnoreCase) ||
                string.Equals(name, "RealGasGiant", StringComparison.OrdinalIgnoreCase) ||
                string.Equals(name, "NULL", StringComparison.OrdinalIgnoreCase) ||
                string.Equals(name, "SPECIAL", StringComparison.OrdinalIgnoreCase))
                return false;

            string lowered = name.ToLowerInvariant();
            if (lowered.Contains("tutorial") || lowered.Contains("example") || lowered.Contains("systemtest") || lowered.Contains("testmap"))
                return false;

            return AllowedPlanets.Contains(name);
        }

        private static void Shuffle<T>(IList<T> list, Random rng)
        {
            for (int i = list.Count - 1; i > 0; i--)
            {
                int j = rng.Next(i + 1);
                T temp = list[i];
                list[i] = list[j];
                list[j] = temp;
            }
        }

        private static double ValidateBody(RssBodyWire body)
        {
            double envelope = body.TerrestrialPlanetInfo == null ? 900000d : body.TerrestrialPlanetInfo.RadiusKm * 6000d;
            var shells = new List<Vector2D>();
            foreach (var child in body.Children)
            {
                double extent = ValidateBody(child);
                if (child.OrbitInfo == null) throw new Exception("Child is missing an orbit.");
                double a = child.OrbitInfo.SemimajorAxis;
                double e = child.OrbitInfo.Eccentricity;
                double inner = a * (1 - e) - extent;
                double outer = a * (1 + e) + extent;
                if (inner <= envelope && shells.Count == 0)
                    throw new Exception("Child orbit intersects its parent.");
                foreach (var shell in shells)
                    if (inner < shell.Y && outer > shell.X)
                        throw new Exception("Orbital envelopes overlap.");
                shells.Add(new Vector2D(inner, outer));
            }
            foreach (var shell in shells) envelope = Math.Max(envelope, shell.Y);
            body.PlanetOrbitZoneRadius = (float)Math.Max(body.PlanetOrbitZoneRadius, envelope * 1.05);
            return body.PlanetOrbitZoneRadius;
        }

        private static void ValidateSector(RssSettingsWire config)
        {
            foreach (var system in config.SolarSystems) ValidateBody(system.RootBody);
            for (int i = 0; i < config.SolarSystems.Count; i++)
                for (int j = i + 1; j < config.SolarSystems.Count; j++)
                {
                    var a = config.SolarSystems[i];
                    var b = config.SolarSystems[j];
                    if (Vector3D.Distance(a.Position, b.Position) <= a.RootBody.PlanetOrbitZoneRadius + b.RootBody.PlanetOrbitZoneRadius)
                        throw new Exception("System zones overlap.");
                }
        }

        private static string GenerateName(Random rng)
        {
            string[] a = { "Al", "Ca", "Da", "Eri", "Ka", "Lor", "Ny", "Or", "Pra", "Sa", "Tal", "Vex", "Wy", "Zen", "Ith", "Kor", "Mer", "Rho" };
            string[] b = { "dor", "ion", "ara", "eus", "eth", "ora", "yx", "aris", "une", "os", "ia", "eron", "alis", "orn", "ek", "uum" };
            return a[rng.Next(a.Length)] + b[rng.Next(b.Length)];
        }

        private static string GenerateUniqueName(SectorBuildContext build)
        {
            for (int attempt = 0; attempt < 100; attempt++)
            {
                string candidate = GenerateName(build.Random);
                if (build.UsedNames.Add(candidate))
                    return candidate;
            }

            string fallback = GenerateName(build.Random) + "-" + build.UsedNames.Count;
            build.UsedNames.Add(fallback);
            return fallback;
        }

        private static List<MyPlanet> GetLoadedPlanets()
        {
            List<IMyVoxelBase> voxels = new List<IMyVoxelBase>();
            MyAPIGateway.Session.VoxelMaps.GetInstances(voxels, v => v is MyPlanet);
            return voxels.OfType<MyPlanet>().ToList();
        }

        private static bool IsServer()
        {
            return MyAPIGateway.Multiplayer == null || MyAPIGateway.Multiplayer.IsServer;
        }

        private void CheckRssAdoptionAndFinishBootstrap()
        {
            if (_ticks < 120)
                return;

            MyPlanet start = FindPlanetByEntityId(_state.StartPlanetEntityId);
            if (start != null && _rss.IsReady && _rss.IsManagedBody(start))
            {
                foreach (long id in _state.GeneratedEntityIds)
                {
                    MyPlanet body = FindPlanetByEntityId(id);
                    if (body == null || !_rss.IsManagedBody(body)) return;
                }
                if (!_startTeleportDone)
                    _startTeleportDone = TeleportCharacterToRssStarter(start);
                if (!_startTeleportDone) return;
                if (!_adoptionNoticeShown)
                {
                    _adoptionNoticeShown = true;
                    Show("RSS successfully adopted the generated sector. Bootstrap is complete.");
                }

                _state.PendingApply = false;
                _state.Applied = true;
                WriteState(_state);
                _pendingAdoptionCheck = false;
                return;
            }

            if (_ticks == 1800)
            {
                Show("RSS has not adopted this sector. Exit the game and complete the local offline handoff before reloading.");
            }
        }

        private static void RollbackGeneratedEntities(SectorBuildContext build)
        {
            if (build == null)
                return;

            for (int i = build.GeneratedEntities.Count - 1; i >= 0; i--)
            {
                try
                {
                    MyPlanet planet = build.GeneratedEntities[i];
                    if (planet != null && !planet.MarkedForClose)
                        planet.Close();
                }
                catch (Exception e)
                {
                    MyLog.Default.WriteLineAndConsole("[RSG] Rollback close failed: " + e.Message);
                }
            }
            build.GeneratedEntities.Clear();
        }

        private static MyPlanet FindPlanetByEntityId(long entityId)
        {
            if (entityId == 0)
                return null;

            List<IMyVoxelBase> voxels = new List<IMyVoxelBase>();
            MyAPIGateway.Session.VoxelMaps.GetInstances(voxels, v => v is MyPlanet);
            for (int i = 0; i < voxels.Count; i++)
            {
                MyPlanet p = voxels[i] as MyPlanet;
                if (p != null && p.EntityId == entityId)
                    return p;
            }
            return null;
        }

        private static void TeleportCharacterToUnmanagedStarter(MyPlanet planet)
        {
            IMyCharacter character = MyAPIGateway.Session == null || MyAPIGateway.Session.Player == null ? null : MyAPIGateway.Session.Player.Character;
            if (character == null || planet == null)
                return;

            Vector3D center = ((IMyEntity)planet).WorldAABB.Center;
            Vector3D radial = Vector3D.Up;
            double radius = ((IMyEntity)planet).WorldAABB.HalfExtents.Max();
            Vector3D probe = center + radial * (radius + 5000d);
            Vector3D surface = planet.GetClosestSurfacePointGlobal(probe) + radial * 8d;
            Vector3D forward = Vector3D.CalculatePerpendicularVector(radial);
            character.Teleport(MatrixD.CreateWorld(surface, forward, radial), null, true);
            if (character.Physics != null)
            {
                character.Physics.LinearVelocity = Vector3.Zero;
                character.Physics.AngularVelocity = Vector3.Zero;
            }
        }

        private bool TeleportCharacterToRssStarter(MyPlanet planet)
        {
            IMyCharacter character = MyAPIGateway.Session == null || MyAPIGateway.Session.Player == null ? null : MyAPIGateway.Session.Player.Character;
            if (character == null || planet == null)
                return false;

            Vector3D center = ((IMyEntity)planet).WorldAABB.Center;
            Vector3D radial = Vector3D.Up;
            double radius = ((IMyEntity)planet).WorldAABB.HalfExtents.Max();
            Vector3D probe = center + radial * (radius + 5000d);
            Vector3D trueSurface = planet.GetClosestSurfacePointGlobal(probe) + radial * 8d;
            Vector3D proxySurface;
            if (!_rss.TryConvertSurfaceToProxy(planet, trueSurface, out proxySurface))
                return false;

            Vector3D forward = Vector3D.CalculatePerpendicularVector(radial);
            character.Teleport(MatrixD.CreateWorld(proxySurface, forward, radial), null, true);
            if (character.Physics != null)
            {
                character.Physics.LinearVelocity = Vector3.Zero;
                character.Physics.AngularVelocity = Vector3.Zero;
            }
            return true;
        }

        private PendingSectorState ReadState()
        {
            try
            {
                if (!MyAPIGateway.Utilities.FileExistsInWorldStorage(StateFileName, typeof(RandomSectorGeneratorSession)))
                    return new PendingSectorState();

                using (TextReader reader = MyAPIGateway.Utilities.ReadFileInWorldStorage(StateFileName, typeof(RandomSectorGeneratorSession)))
                {
                    string xml = reader.ReadToEnd();
                    PendingSectorState state = MyAPIGateway.Utilities.SerializeFromXML<PendingSectorState>(xml);
                    return state ?? new PendingSectorState();
                }
            }
            catch (Exception e)
            {
                MyLog.Default.WriteLineAndConsole("[RSG] Failed to read state: " + e);
                return new PendingSectorState { Failed = true };
            }
        }

        private void WriteState(PendingSectorState state)
        {
            try
            {
                string xml = MyAPIGateway.Utilities.SerializeToXML(state);
                using (TextWriter writer = MyAPIGateway.Utilities.WriteFileInWorldStorage(StateFileName, typeof(RandomSectorGeneratorSession)))
                    writer.Write(xml);
            }
            catch (Exception e)
            {
                MyLog.Default.WriteLineAndConsole("[RSG] Failed to write state: " + e);
                throw;
            }
        }

        private void WriteManifest(SectorBuildContext build, List<MyPlanetGeneratorDefinition> definitions, int seed, string blackHoleSkin)
        {
            try
            {
                StringBuilder sb = new StringBuilder();
                sb.AppendLine("Random Sector Generator debug manifest");
                sb.AppendLine("Seed: " + seed);
                sb.AppendLine("Root systems: " + build.Config.SolarSystems.Count);
                sb.AppendLine("Physical stars: " + build.Stars.Count);
                sb.AppendLine("Black hole: " + (build.BlackHole != null));
                sb.AppendLine("Black hole skin: " + (blackHoleSkin ?? "<none>"));
                sb.AppendLine("Gas giants incl. black hole: " + build.GasGiantCount);
                sb.AppendLine("Starter: " + (build.StartPlanet == null ? "<none>" : build.StartPlanet.Name));
                sb.AppendLine();
                sb.AppendLine("Generated hierarchy (SPOILER / DEBUG):");
                for (int i = 0; i < build.Config.SolarSystems.Count; i++)
                {
                    RssSolarSystemWire system = build.Config.SolarSystems[i];
                    sb.AppendLine("System " + (i + 1) + " root @ " + system.Position);
                    AppendBodyManifest(sb, system.RootBody, "  ");
                }
                sb.AppendLine();
                sb.AppendLine("Planet display-name -> subtype (SPOILER / DEBUG):");
                foreach (KeyValuePair<string, string> pair in build.PlanetSubtypeByName.OrderBy(x => x.Key))
                    sb.AppendLine(pair.Key + " -> " + pair.Value);
                sb.AppendLine();
                sb.AppendLine("Enabled definitions used:");
                foreach (MyPlanetGeneratorDefinition def in definitions)
                    sb.AppendLine(def.Id.SubtypeId.ToString());

                using (TextWriter writer = MyAPIGateway.Utilities.WriteFileInWorldStorage(ManifestFileName, typeof(RandomSectorGeneratorSession)))
                    writer.Write(sb.ToString());
            }
            catch (Exception e)
            {
                MyLog.Default.WriteLineAndConsole("[RSG] Failed to write manifest: " + e);
                throw;
            }
        }

        private static void AppendBodyManifest(StringBuilder sb, RssBodyWire body, string indent)
        {
            if (body == null)
                return;

            string orbit = body.OrbitInfo == null ? "root" : ("a=" + body.OrbitInfo.SemimajorAxis + "m e=" + body.OrbitInfo.Eccentricity.ToString("0.000"));
            sb.AppendLine(indent + body.Name + " [" + body.PlanetTypeId + "] " + orbit + " instance=" + body.BodyInstanceName);
            if (body.Sibling != null)
            {
                sb.AppendLine(indent + "  sibling:");
                AppendBodyManifest(sb, body.Sibling, indent + "    ");
            }
            if (body.Children != null)
            {
                for (int i = 0; i < body.Children.Count; i++)
                    AppendBodyManifest(sb, body.Children[i], indent + "  ");
            }
        }

        private static void Show(string message)
        {
            if (MyAPIGateway.Utilities != null)
                MyAPIGateway.Utilities.ShowMessage(Author, message);
        }

        private sealed class SectorBuildContext
        {
            public readonly Random Random;
            public readonly RssSettingsWire Config;
            public readonly List<StarBuildNode> Stars = new List<StarBuildNode>();
            public readonly Dictionary<string, string> PlanetSubtypeByName = new Dictionary<string, string>();
            public readonly List<MyPlanet> GeneratedEntities = new List<MyPlanet>();
            public readonly HashSet<string> UsedNames = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            public MyPlanet BlackHole;
            public RssBodyWire BlackHoleBody;
            public MyPlanet StartPlanet;
            public int GasGiantCount;

            public SectorBuildContext(Random random, RssSettingsWire config)
            {
                Random = random;
                Config = config;
            }
        }

        private sealed class StarBuildNode
        {
            public MyPlanet Entity;
            public RssBodyWire Body;
            public string Name;
            public RssBodyWire GasGiantBody;
            public RssBodyWire LastDirectPlanet;
        }
    }
}
