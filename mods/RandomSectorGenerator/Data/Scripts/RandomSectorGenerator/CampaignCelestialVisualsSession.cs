using Sandbox.Game.Entities;
using Sandbox.ModAPI;
using System;
using System.Collections.Generic;
using VRage.Game;
using VRage.Game.Components;
using VRage.ModAPI;
using VRage.Utils;
using VRageMath;
using BlendTypeEnum = VRageRender.MyBillboard.BlendTypeEnum;

namespace RandomSectorGenerator
{
    /// <summary>
    /// Client-only astronomical visual supplement.
    ///
    /// Real Stars intentionally stops its native glare at 200,000 km. The campaign
    /// spans roughly 1.35 million km from the central black hole, so remote stars
    /// otherwise disappear even though RSS still tracks them. This component draws
    /// tiny point-like stars using RSS proxy positions beyond the native glare range.
    ///
    /// It also draws a small, distant-only S-star cluster around the central black
    /// hole. These are visual scale cues, not visitable celestial bodies; they fade
    /// away long before the player reaches the black-hole region.
    /// </summary>
    [MySessionComponentDescriptor(MyUpdateOrder.AfterSimulation)]
    public sealed class CampaignCelestialVisualsSession : MySessionComponentBase
    {
        private const double NativeGlareRangeM = 200000000d;
        private const double DistantStarFadeStartM = 175000000d;
        private const double DistantStarFullM = 225000000d;
        private const double DistantStarFarFadeStartM = 2500000000d;
        private const double DistantStarFarEndM = 3000000000d;
        private const double RenderShellDistanceM = 50000d;

        private const double ClusterFadeStartM = 100000000d;
        private const double ClusterFullM = 150000000d;
        private const double ClusterFarEndM = 3000000000d;

        private readonly RealStarsClient _realStars = new RealStarsClient();
        private readonly RealSolarSystemsClient _rss = new RealSolarSystemsClient();
        private readonly List<MyPlanet> _stars = new List<MyPlanet>();

        private readonly MyStringId _glowMaterial = MyStringId.GetOrCompute("SunBigGlow");
        private readonly MyStringId _rayMaterial = MyStringId.GetOrCompute("SunBigRays");

        private MyPlanet _blackHole;
        private int _ticks;

        private static readonly SyntheticStar[] SStars =
        {
            new SyntheticStar(6000000d, 1200d, 0.10d, 0.25d, new Color(205, 225, 255), 0.80f),
            new SyntheticStar(9000000d, 2100d, 1.70d, -0.35d, new Color(255, 244, 214), 0.75f),
            new SyntheticStar(13500000d, 3300d, 3.20d, 0.55d, new Color(190, 215, 255), 0.70f),
            new SyntheticStar(18000000d, 4800d, 4.80d, -0.70d, new Color(255, 204, 150), 0.65f),
        };

        public override void LoadData()
        {
            _realStars.Load();
            _rss.Load();
        }

        protected override void UnloadData()
        {
            _realStars.Unload();
            _rss.Unload();
            _stars.Clear();
            _blackHole = null;
        }

        public override void UpdateAfterSimulation()
        {
            if (MyAPIGateway.Utilities == null || MyAPIGateway.Utilities.IsDedicated ||
                MyAPIGateway.Session == null || MyAPIGateway.Session.Camera == null)
                return;

            _ticks++;

            if ((_ticks % 180) == 0)
            {
                if (!_realStars.IsReady && !_realStars.Compromised)
                    _realStars.Load();
                if (!_rss.IsReady && !_rss.Compromised)
                    _rss.Load();
            }

            if (!_realStars.IsReady || !_rss.IsReady)
                return;

            if ((_ticks % 600) == 1 || (_stars.Count == 0 && _ticks > 120))
                RefreshBodies();

            Vector3D proxyCamera = _rss.GetCurrentCameraProxyPosition();
            DrawRealStars(proxyCamera);
            DrawSyntheticBlackHoleCluster(proxyCamera);
        }

        private void RefreshBodies()
        {
            _stars.Clear();
            _blackHole = null;

            HashSet<IMyEntity> entities = new HashSet<IMyEntity>();
            MyAPIGateway.Entities.GetEntities(entities, entity => entity is MyPlanet);
            foreach (IMyEntity entity in entities)
            {
                MyPlanet planet = entity as MyPlanet;
                if (planet == null)
                    continue;

                float radiusKm;
                Vector3I color;
                float effectBrightness;
                float lightBrightness;
                float damageRadiusKm;
                if (_realStars.TryGetStarInfo(planet, out radiusKm, out color, out effectBrightness,
                    out lightBrightness, out damageRadiusKm))
                {
                    _stars.Add(planet);
                    continue;
                }

                if (!string.IsNullOrEmpty(planet.Name) &&
                    planet.Name.EndsWith(" Abyss", StringComparison.OrdinalIgnoreCase) &&
                    _rss.IsManagedBody(planet))
                {
                    _blackHole = planet;
                }
            }
        }

        private void DrawRealStars(Vector3D proxyCamera)
        {
            for (int i = 0; i < _stars.Count; i++)
            {
                MyPlanet star = _stars[i];
                if (star == null || !star.InScene)
                    continue;

                Vector3D proxyPosition;
                MatrixD proxyRotation;
                double surfaceRange;
                double orbitRange;
                if (!_rss.TryGetBodyProxyState(star, out proxyPosition, out proxyRotation, out surfaceRange, out orbitRange))
                    continue;

                Vector3D toStar = proxyPosition - proxyCamera;
                double distance = toStar.Length();
                if (distance <= DistantStarFadeStartM || distance >= DistantStarFarEndM)
                    continue;

                float radiusKm;
                Vector3I color;
                float effectBrightness;
                float lightBrightness;
                float damageRadiusKm;
                if (!_realStars.TryGetStarInfo(star, out radiusKm, out color, out effectBrightness,
                    out lightBrightness, out damageRadiusKm))
                    continue;

                float nearFade = SmoothStep((float)((distance - DistantStarFadeStartM) /
                    (DistantStarFullM - DistantStarFadeStartM)));
                float farFade = 1f;
                if (distance > DistantStarFarFadeStartM)
                {
                    farFade = 1f - SmoothStep((float)((distance - DistantStarFarFadeStartM) /
                        (DistantStarFarEndM - DistantStarFarFadeStartM)));
                }

                float fade = MathHelper.Clamp(nearFade * farFade, 0f, 1f);
                if (fade <= 0.001f)
                    continue;

                float brightness = MathHelper.Clamp(effectBrightness, 0.4f, 2f);
                float radius = (float)Math.Sqrt(NativeGlareRangeM / distance) * 34f;
                radius = MathHelper.Clamp(radius, 12f, 32f);

                Color drawColor = new Color(
                    (byte)MathHelper.Clamp(color.X, 0, 255),
                    (byte)MathHelper.Clamp(color.Y, 0, 255),
                    (byte)MathHelper.Clamp(color.Z, 0, 255));
                drawColor *= fade * MathHelper.Clamp(brightness / 1.5f, 0.45f, 1f);

                DrawPoint(proxyPosition, proxyCamera, drawColor, radius, true);
            }
        }

        private void DrawSyntheticBlackHoleCluster(Vector3D proxyCamera)
        {
            if (_blackHole == null || !_blackHole.InScene)
                return;

            Vector3D blackHolePosition;
            MatrixD blackHoleRotation;
            double surfaceRange;
            double orbitRange;
            if (!_rss.TryGetBodyProxyState(_blackHole, out blackHolePosition, out blackHoleRotation,
                out surfaceRange, out orbitRange))
                return;

            double cameraDistance = Vector3D.Distance(proxyCamera, blackHolePosition);
            if (cameraDistance <= ClusterFadeStartM || cameraDistance >= ClusterFarEndM)
                return;

            float fade = SmoothStep((float)((cameraDistance - ClusterFadeStartM) /
                (ClusterFullM - ClusterFadeStartM)));
            fade = MathHelper.Clamp(fade, 0f, 1f);

            double seconds = MyAPIGateway.Session.ElapsedPlayTime.TotalSeconds;
            for (int i = 0; i < SStars.Length; i++)
            {
                SyntheticStar item = SStars[i];
                double angle = item.Phase + (seconds / item.PeriodSeconds) * Math.PI * 2d;
                double cos = Math.Cos(angle);
                double sin = Math.Sin(angle);

                Vector3D local = new Vector3D(
                    cos * item.OrbitRadiusM,
                    sin * item.OrbitRadiusM,
                    Math.Sin(angle * 0.5d + item.Phase) * item.OrbitRadiusM * 0.12d);

                MatrixD tilt = MatrixD.CreateRotationX(item.TiltRadians) *
                               MatrixD.CreateRotationZ(item.Phase * 0.35d);
                Vector3D proxyPosition = blackHolePosition + Vector3D.TransformNormal(local, tilt);

                Color color = item.Color;
                color *= fade * item.Brightness;
                DrawPoint(proxyPosition, proxyCamera, color, 10f + i * 1.5f, false);
            }
        }

        private void DrawPoint(Vector3D proxyTarget, Vector3D proxyCamera, Color color, float radius, bool addRays)
        {
            Vector3D direction = proxyTarget - proxyCamera;
            double length = direction.Normalize();
            if (length <= 1d || double.IsNaN(length))
                return;

            MatrixD cameraMatrix = MyAPIGateway.Session.Camera.WorldMatrix;
            Vector3D drawPosition = cameraMatrix.Translation + direction * RenderShellDistanceM;
            Vector3 left = (Vector3)cameraMatrix.Left;
            Vector3 up = (Vector3)cameraMatrix.Up;

            MyTransparentGeometry.AddBillboardOriented(
                _glowMaterial, color, drawPosition, left, up, radius, BlendTypeEnum.AdditiveBottom);

            if (addRays)
            {
                Color rays = color;
                rays *= 0.35f;
                MyTransparentGeometry.AddBillboardOriented(
                    _rayMaterial, rays, drawPosition, left, up, radius * 1.8f, BlendTypeEnum.AdditiveBottom);
            }
        }

        private static float SmoothStep(float value)
        {
            value = MathHelper.Clamp(value, 0f, 1f);
            return value * value * (3f - 2f * value);
        }

        private struct SyntheticStar
        {
            public readonly double OrbitRadiusM;
            public readonly double PeriodSeconds;
            public readonly double Phase;
            public readonly double TiltRadians;
            public readonly Color Color;
            public readonly float Brightness;

            public SyntheticStar(double orbitRadiusM, double periodSeconds, double phase,
                double tiltRadians, Color color, float brightness)
            {
                OrbitRadiusM = orbitRadiusM;
                PeriodSeconds = periodSeconds;
                Phase = phase;
                TiltRadians = tiltRadians;
                Color = color;
                Brightness = brightness;
            }
        }
    }
}
