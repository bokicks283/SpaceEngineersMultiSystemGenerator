using Sandbox.Common.ObjectBuilders;
using Sandbox.Definitions;
using Sandbox.ModAPI;
using System;
using System.IO;
using VRage.Game;
using VRage.Game.Components;
using VRage.Utils;

namespace RandomSectorGenerator
{
    /// <summary>
    /// Small campaign-only definition tune for the two strategic jump-drive tiers.
    /// Values live in world storage so the campaign can be retuned without
    /// rebuilding the mod. The default physical-flight layer remains RTS.
    /// </summary>
    [MySessionComponentDescriptor(MyUpdateOrder.NoUpdate)]
    public sealed class CampaignTravelTuningSession : MySessionComponentBase
    {
        private const string ConfigFileName = "CampaignTravelTuning.xml";
        private CampaignTravelTuningConfig _config;

        public override void LoadData()
        {
            _config = LoadConfig();
            Apply("LargeJumpDrive",
                _config.NormalJumpMaxDistanceM,
                _config.NormalJumpMaxMassKg,
                _config.NormalJumpRequiredPowerMW,
                _config.NormalJumpStoredEnergyMWh,
                false);

            Apply("HyperDrive",
                _config.HyperDriveMaxDistanceM,
                _config.HyperDriveMaxMassKg,
                _config.HyperDriveRequiredPowerMW,
                _config.HyperDriveStoredEnergyMWh,
                true);
        }

        private CampaignTravelTuningConfig LoadConfig()
        {
            CampaignTravelTuningConfig config = new CampaignTravelTuningConfig();
            try
            {
                if (MyAPIGateway.Utilities.FileExistsInWorldStorage(ConfigFileName, typeof(CampaignTravelTuningConfig)))
                {
                    using (TextReader reader = MyAPIGateway.Utilities.ReadFileInWorldStorage(ConfigFileName, typeof(CampaignTravelTuningConfig)))
                    {
                        CampaignTravelTuningConfig loaded = MyAPIGateway.Utilities.SerializeFromXML<CampaignTravelTuningConfig>(reader.ReadToEnd());
                        if (loaded != null)
                            config = loaded;
                    }
                }

                config.Sanitize();

                if (MyAPIGateway.Session != null && MyAPIGateway.Session.IsServer)
                {
                    using (TextWriter writer = MyAPIGateway.Utilities.WriteFileInWorldStorage(ConfigFileName, typeof(CampaignTravelTuningConfig)))
                    {
                        writer.Write(MyAPIGateway.Utilities.SerializeToXML(config));
                    }
                }
            }
            catch (Exception exc)
            {
                MyLog.Default.WriteLineAndConsole("[RSG Travel] Failed to load/save travel tuning; using defaults: " + exc.Message);
                config = new CampaignTravelTuningConfig();
            }
            return config;
        }

        private static void Apply(
            string subtype,
            double maxDistanceM,
            double maxMassKg,
            float requiredPowerMW,
            float storedEnergyMWh,
            bool optional)
        {
            try
            {
                MyDefinitionId id = new MyDefinitionId(typeof(MyObjectBuilder_JumpDrive), subtype);
                MyJumpDriveDefinition definition = MyDefinitionManager.Static.GetCubeBlockDefinition(id) as MyJumpDriveDefinition;
                if (definition == null)
                {
                    if (!optional)
                        MyLog.Default.WriteLineAndConsole("[RSG Travel] Missing required jump-drive definition: " + id);
                    else
                        MyLog.Default.WriteLineAndConsole("[RSG Travel] Optional HyperDrive definition is not loaded.");
                    return;
                }

                definition.MaxJumpDistance = maxDistanceM;
                definition.MaxJumpMass = maxMassKg;
                definition.RequiredPowerInput = requiredPowerMW;
                definition.PowerNeededForJump = storedEnergyMWh;

                MyLog.Default.WriteLineAndConsole(
                    string.Format(
                        "[RSG Travel] {0}: range={1:N0} km mass={2:N0} kg input={3:0.##} MW energy={4:0.##} MWh",
                        subtype,
                        maxDistanceM / 1000d,
                        maxMassKg,
                        requiredPowerMW,
                        storedEnergyMWh));
            }
            catch (Exception exc)
            {
                MyLog.Default.WriteLineAndConsole("[RSG Travel] Failed to tune " + subtype + ": " + exc.Message);
            }
        }
    }

    public sealed class CampaignTravelTuningConfig
    {
        public double NormalJumpMaxDistanceM = 50000000d;
        public double NormalJumpMaxMassKg = 1250000d;
        public float NormalJumpRequiredPowerMW = 64f;
        public float NormalJumpStoredEnergyMWh = 1.2f;

        public double HyperDriveMaxDistanceM = 2500000000d;
        public double HyperDriveMaxMassKg = 25600000d;
        public float HyperDriveRequiredPowerMW = 250f;
        public float HyperDriveStoredEnergyMWh = 10f;

        public void Sanitize()
        {
            NormalJumpMaxDistanceM = Clamp(NormalJumpMaxDistanceM, 2000000d, 250000000d);
            NormalJumpMaxMassKg = Clamp(NormalJumpMaxMassKg, 100000d, 100000000d);
            NormalJumpRequiredPowerMW = Clamp(NormalJumpRequiredPowerMW, 1f, 1000f);
            NormalJumpStoredEnergyMWh = Clamp(NormalJumpStoredEnergyMWh, 0.1f, 100f);

            HyperDriveMaxDistanceM = Clamp(HyperDriveMaxDistanceM, 100000000d, 5000000000d);
            HyperDriveMaxMassKg = Clamp(HyperDriveMaxMassKg, 1000000d, 250000000d);
            HyperDriveRequiredPowerMW = Clamp(HyperDriveRequiredPowerMW, 1f, 5000f);
            HyperDriveStoredEnergyMWh = Clamp(HyperDriveStoredEnergyMWh, 0.1f, 500f);
        }

        private static double Clamp(double value, double min, double max)
        {
            return Math.Max(min, Math.Min(max, value));
        }

        private static float Clamp(float value, float min, float max)
        {
            return Math.Max(min, Math.Min(max, value));
        }
    }
}
