my $hvPktCount = -1;

while (<>) {
    chomp;
    /(\d+),/ or die;
    my $cur = int $1;
    printf("$.: bad %d -> %d\n", $prev, $cur) if ($prev >= 0 && $cur - $prev != 1);
    $prev = $cur;
}
