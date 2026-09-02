export const F = () => (
  <p>
    설명입니다, 이어집니다.
    {목록.map((항목) => (
      <span key={항목.id}>{항목.이름}</span>
    ))}
  </p>
);
