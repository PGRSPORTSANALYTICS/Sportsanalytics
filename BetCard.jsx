export default function BetCard({
  matchup,
  kickoff,
  ev,
  odds,
  stake,
  legs = [],
  type = "",
}) {
  const evPositive = ev >= 0;

  return (
    <div className="w-full bg-[#0B0F10] border border-[#1F3D2E]/40 rounded-xl p-5 shadow-[0_0_25px_-5px_rgba(32,255,125,0.25)] hover:shadow-[0_0_35px_-2px_rgba(32,255,125,0.4)] transition-all duration-300 mb-6">

      {/* MATCHUP */}
      <p className="text-white text-lg font-semibold">
        {matchup}
      </p>

      {/* KO + TYPE */}
      <p className="text-gray-400 text-sm mt-1">
        Kickoff: {kickoff}
      </p>

      {type && (
        <p className="text-green-300 text-sm font-medium mt-1">
          {type}
        </p>
      )}

      {/* EV BADGE */}
      <div className="flex justify-end mt-3">
        <div
          className={`px-3 py-1 rounded-full text-xs font-semibold ${
            evPositive
              ? "bg-green-500/20 text-green-400 border border-green-500/30"
              : "bg-red-500/20 text-red-400 border border-red-500/30"
          }`}
        >
          EV {evPositive ? "+" : ""}{ev}%
        </div>
      </div>

      {/* LEGS (SGP) */}
      {legs.length > 0 && (
        <div className="mt-3">
          <p className="text-gray-400 text-xs">SGP legs:</p>
          <ul className="text-white text-sm mt-1 space-y-1">
            {legs.map((leg, i) => (
              <li key={i}>• {leg}</li>
            ))}
          </ul>
        </div>
      )}

      {/* ODDS + STAKE */}
      <div className="flex justify-between items-center mt-5">
        <div>
          <p className="text-gray-400 text-xs">ODDS</p>
          <p className="text-white text-xl font-bold">{odds}</p>
        </div>

        <div>
          <p className="text-gray-400 text-xs">STAKE</p>
          <p className="text-white text-xl font-bold">{stake} kr</p>
        </div>

        <button className="bg-green-500/10 hover:bg-green-500/20 text-green-300 font-semibold text-sm px-4 py-2 rounded-xl transition-all">
          Track
        </button>
      </div>
    </div>
  );
}